"""Roadmap, what-if scenarios, forecasts, epic breakdown and sprint planning."""

from __future__ import annotations

import re
import uuid
from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession

from twinpm.core.errors import AppError, NotFoundError
from twinpm.core.tenancy import TenantContext
from twinpm.db import models as m
from twinpm.db.repository import Repo
from twinpm.domain import SPRINT_DAYS, capacity_points
from twinpm.ml import forecast, scenario
from twinpm.ml.features import FeatureBuilder
from twinpm.schemas.planning import (
    BreakdownOut,
    ForecastBand,
    ForecastOut,
    InitiativeCard,
    ProposedStory,
    RoadmapOut,
    SimulateOut,
    SprintPlanOut,
)
from twinpm.services import actions, ml_jobs, suggestions
from twinpm.services.data_cache import get_program_data
from twinpm.services.program import forecasts as forecast_rows

MEETING_SHARE = 0.15  # ceremonies and meetings take ~15% of sprint capacity


async def roadmap(session: AsyncSession, ctx: TenantContext, program_id: uuid.UUID) -> RoadmapOut:
    await Repo(session, ctx, m.Program).get(program_id)
    data = await get_program_data(session, ctx.org_id, program_id)
    risks = await ml_jobs.latest_risks(session, ctx.org_id)
    inis = await Repo(session, ctx, m.Initiative).all(m.Initiative.program_id == program_id)
    objectives = {o.id: o.title for o in await Repo(session, ctx, m.Objective).all()}
    epics = data.epics
    it = data.items
    deps = data.deps
    epic_ids_by_ini = {
        i: set(epics.loc[epics["initiative_id"] == i, "id"])
        for i in epics["initiative_id"].dropna().unique()
    }
    buckets: dict[str, list[InitiativeCard]] = {"now": [], "next": [], "later": []}
    for ini in inis:
        eids = epic_ids_by_ini.get(ini.id, set())
        open_items = it[it["epic_id"].isin(eids) & (it["status"] != "done")]
        risk = (
            float(np.mean([risks.get(w, 0.0) for w in open_items["id"]]))
            if len(open_items)
            else 0.0
        )
        dep_count = int(
            ((deps["from_id"].isin(eids | {ini.id})) | (deps["to_id"].isin(eids | {ini.id}))).sum()
        )
        ep = [
            {
                "id": str(r.id),
                "title": r.title,
                "status": r.status,
                "open_items": int(((it["epic_id"] == r.id) & (it["status"] != "done")).sum()),
            }
            for r in epics[epics["id"].isin(eids)].itertuples()
        ]
        buckets[ini.roadmap_bucket].append(
            InitiativeCard(
                id=ini.id,
                title=ini.title,
                description=ini.description,
                roadmap_bucket=ini.roadmap_bucket,
                rice=ini.rice,
                wsjf=ini.wsjf,
                target_date=ini.target_date,
                status=ini.status,
                objective=objectives.get(ini.objective_id) if ini.objective_id else None,
                dependency_count=dep_count,
                risk=round(risk, 3),
                epics=ep,
            )
        )
    for cards in buckets.values():
        cards.sort(key=lambda c: -float(c.rice.get("score", 0)))
    return RoadmapOut(program_id=program_id, buckets=buckets)


async def patch_initiative(
    session: AsyncSession,
    ctx: TenantContext,
    initiative_id: uuid.UUID,
    changes: dict[str, Any],
    reason: str | None,
) -> dict[str, Any]:
    payload = {"initiative_id": str(initiative_id), **changes}
    return await actions.execute(session, ctx, "roadmap_change", payload)


def _band(r: forecast.ForecastResult) -> ForecastBand:
    return ForecastBand(p50=r.p50, p80=r.p80, p95=r.p95, on_time_probability=r.on_time_probability)


async def simulate(
    session: AsyncSession,
    ctx: TenantContext,
    program_id: uuid.UUID,
    changes: list[dict[str, Any]],
) -> SimulateOut:
    _, milestone = await ml_jobs.program_context(session, ctx.org_id)
    data = await get_program_data(session, ctx.org_id, program_id)
    risks = await ml_jobs.latest_risks(session, ctx.org_id)
    dm, _ = ml_jobs.get_models()
    inp = forecast.build_input(data, milestone.id, risks)
    known_items = set(data.items["id"].astype(str))
    for ch in changes:
        for w in ch.get("work_item_ids", []):
            if str(w) not in known_items:
                raise NotFoundError(f"Work item {w} not found")
    res = scenario.run(data, inp, changes, dm)
    titles = data.epics.set_index("id")["title"].to_dict()
    shifted = scenario.apply_changes(data, inp, [c for c in changes if c["type"] == "date_shift"])
    return SimulateOut(
        baseline=_band(res.baseline),
        scenario=_band(res.scenario),
        target_date=shifted.target,
        delta_days=res.delta_days,
        risk_delta=res.risk_delta,
        capacity_delta=res.capacity_delta,
        affected_epics=[
            {
                "id": e,
                "title": titles.get(uuid.UUID(e), e),
                "baseline_p80": res.baseline.epic_p80[e].isoformat(),
                "scenario_p80": res.scenario.epic_p80.get(e, res.baseline.epic_p80[e]).isoformat(),
            }
            for e in res.affected_epics
            if e in res.baseline.epic_p80
        ],
        narrative=res.narrative,
        histogram=res.scenario.histogram,
        baseline_histogram=res.baseline.histogram,
    )


async def save_scenario(
    session: AsyncSession,
    ctx: TenantContext,
    program_id: uuid.UUID,
    name: str,
    changes: list[dict[str, Any]],
) -> m.Scenario:
    result = await simulate(session, ctx, program_id, changes)
    out = await actions.execute(
        session,
        ctx,
        "scenario",
        {"name": name, "changes": changes, "result": result.model_dump(mode="json")},
    )
    return await Repo(session, ctx, m.Scenario).get(uuid.UUID(out["scenario_id"]))


async def get_forecast(
    session: AsyncSession, ctx: TenantContext, milestone_id: uuid.UUID
) -> ForecastOut:
    ms = await Repo(session, ctx, m.Milestone).get(milestone_id)
    latest, previous = await forecast_rows(session, ms.id)
    if latest is None:
        await run_forecast(session, ctx, ms.id)
        latest, previous = await forecast_rows(session, ms.id)
    assert latest is not None
    return ForecastOut(
        milestone_id=ms.id,
        milestone=ms.name,
        target_date=ms.target_date,
        p50=latest.p50_date,
        p80=latest.p80_date,
        p95=latest.p95_date,
        on_time_probability=latest.distribution.get("on_time_probability"),
        histogram=latest.distribution.get("histogram", []),
        epic_p80=latest.distribution.get("epic_p80", {}),
        assumptions=latest.assumptions,
        run_at=latest.run_at,
        previous=ForecastBand(p50=previous.p50_date, p80=previous.p80_date, p95=previous.p95_date)
        if previous
        else None,
        previous_run_at=previous.run_at if previous else None,
    )


async def run_forecast(session: AsyncSession, ctx: TenantContext, milestone_id: uuid.UUID) -> None:
    ms = await Repo(session, ctx, m.Milestone).get(milestone_id)
    data = await get_program_data(session, ctx.org_id, ms.program_id)
    risks = await ml_jobs.latest_risks(session, ctx.org_id)
    await ml_jobs.run_forecast(session, data, ms, risks)
    await session.flush()


# --------------------------------------------------------------------------- breakdown
_SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")
VERBS = ("Implement", "Add", "Build", "Validate", "Instrument", "Document", "Test")


def _story_candidates(text: str, title: str) -> list[str]:
    """Deterministic decomposition: bullet points and imperative sentences become stories."""
    bullets = [
        ln.strip("-*• \t").strip()
        for ln in text.splitlines()
        if ln.strip().startswith(("-", "*", "•"))
    ]
    parts = bullets or [s.strip() for s in _SENTENCE.split(text) if len(s.split()) >= 4]
    stories: list[str] = []
    for p in parts:
        p = re.sub(r"\s+", " ", p).rstrip(".")
        if len(p) < 8:
            continue
        if not p.split()[0].istitle() or p.split()[0] not in VERBS:
            p = f"{VERBS[len(stories) % 3]} {p[0].lower()}{p[1:]}"
        stories.append(p[:120])
    if len(stories) < 3:
        stories += [
            f"Implement the core of {title}",
            f"Add tests and monitoring for {title}",
            f"Document and roll out {title} behind a feature flag",
        ]
    return stories[:8]


async def breakdown(
    session: AsyncSession,
    ctx: TenantContext,
    epic_id: uuid.UUID | None,
    text: str | None,
) -> BreakdownOut:
    if epic_id is None and not text:
        raise AppError("Provide epic_id or text")
    epic = await Repo(session, ctx, m.Epic).get(epic_id) if epic_id else None
    title = epic.title if epic else (text or "")[:60]
    body = text or (epic.description if epic else "")
    program, _ = await ml_jobs.program_context(session, ctx.org_id)
    _, em = ml_jobs.get_models()
    titles = _story_candidates(body, title)
    rows = pd.DataFrame(
        {
            "story_points": [3.0] * len(titles),
            "type": ["story"] * len(titles),
            "team_id": [str(epic.team_id) if epic else ""] * len(titles),
            "labels": [[]] * len(titles),
        }
    )
    ests = em.estimate(rows, [f"{t}. {title}" for t in titles])
    stories: list[ProposedStory] = []
    ids: list[uuid.UUID] = []
    for t, e in zip(titles, ests, strict=True):
        pts = float(min([1, 2, 3, 5, 8], key=lambda p: abs(p - e["estimate_days"] / 1.2)))
        ac = [
            f"Given the {title} flow, when {t[0].lower() + t[1:]}, then it behaves as specified",
            "Covered by automated tests and reviewed",
            "Released behind a feature flag",
        ]
        st = ProposedStory(
            title=t,
            description=f"{t}. Part of {title}.",
            acceptance_criteria=ac,
            type="story",
            story_points=pts,
            estimate_days=e["estimate_days"],
            p10_days=e["p10_days"],
            p90_days=e["p90_days"],
            similar=e["similar"],
        )
        stories.append(st)
        if epic is not None:
            s = await suggestions.create(
                session,
                ctx,
                type="create_task",
                agent="planner",
                title=f"Create story: {t}",
                payload={
                    "epic_id": str(epic.id),
                    "title": t,
                    "description": st.description,
                    "story_points": pts,
                    "estimate_days": e["estimate_days"],
                    "acceptance_criteria": ac,
                },
                explanation=f"Estimated {e['estimate_days']} days (80% interval "
                f"{e['p10_days']}-{e['p90_days']}), based on similar past items.",
                citations=[{"type": "epic", "id": str(epic.id), "label": epic.title}]
                + [{"type": "work_item", "id": x["id"], "label": x["key"]} for x in e["similar"]],
                program_id=program.id,
            )
            if s is not None:
                ids.append(s.id)
    return BreakdownOut(epic_id=epic.id if epic else None, stories=stories, suggestion_ids=ids)


async def sprint_plan(
    session: AsyncSession,
    ctx: TenantContext,
    team_id: uuid.UUID,
    sprint_id: uuid.UUID | None,
) -> SprintPlanOut:
    team = await Repo(session, ctx, m.Team).get(team_id)
    program, _ = await ml_jobs.program_context(session, ctx.org_id)
    data = await get_program_data(session, ctx.org_id, program.id)
    sprints = data.sprints[data.sprints["team_id"] == team_id].sort_values("start_date")
    if sprint_id is not None:
        sp = sprints[sprints["id"] == sprint_id]
        if sp.empty:
            raise NotFoundError("Sprint not found")
        start = sp.iloc[0]["start_date"]
        name = str(sp.iloc[0]["name"])
    else:
        last = sprints.iloc[-1]
        start = last["start_date"] + timedelta(days=SPRINT_DAYS)
        name = f"{team.name} Sprint {len(sprints) + 1}"
    end = start + timedelta(days=SPRINT_DAYS - 1)
    members = data.people[data.people["team_id"] == team_id]
    cap = float(sum(capacity_points(float(c)) for c in members["capacity_hours_per_week"]))
    pto = 0.0
    notes = []
    for r in data.time_off.itertuples():
        if r.person_id in set(members["id"]) and r.start_date <= end and r.end_date >= start:
            overlap = (min(r.end_date, end) - max(r.start_date, start)).days + 1
            person = members.set_index("id").loc[r.person_id]
            days_pts = (
                capacity_points(float(person["capacity_hours_per_week"])) / 10 * min(overlap, 10)
            )
            pto += days_pts
            notes.append(f"{person['name']} is out {overlap} day(s) ({r.start_date:%b %d}).")
    meetings = round(cap * MEETING_SHARE, 1)
    fb = FeatureBuilder(data)
    v = fb.sprint_velocities(team_id, pd.Timestamp(data.now), 6)
    hist = float(np.mean(v)) if v else cap * 0.7
    available = max(cap - pto - meetings, 0.0)
    recommended = round(min(available, hist * (available / max(cap - meetings, 1))), 1)
    if v and v[-1] < 0.8 * hist:
        notes.append(
            f"Last sprint delivered {v[-1]:.0f} points vs a {hist:.0f}-point average; "
            "commit conservatively."
        )
    risks = await ml_jobs.latest_risks(session, ctx.org_id)
    backlog = data.items[(data.items["team_id"] == team_id) & (data.items["status"] == "todo")]
    backlog = backlog.assign(risk=backlog["id"].map(lambda w: risks.get(w, 0.3)))
    backlog = backlog.sort_values(["due_date", "risk"], ascending=[True, False])
    rec: list[dict[str, Any]] = []
    stretch: list[dict[str, Any]] = []
    total = 0.0
    for r in backlog.itertuples():
        entry = {
            "id": str(r.id),
            "key": r.key,
            "title": r.title,
            "points": r.story_points,
            "due_date": r.due_date.isoformat() if isinstance(r.due_date, date) else None,
        }
        if total + r.story_points <= recommended:
            rec.append(entry)
            total += r.story_points
        elif len(stretch) < 3:
            stretch.append(entry)
    return SprintPlanOut(
        team_id=team_id,
        sprint=name,
        capacity_points=round(cap, 1),
        pto_points=round(pto, 1),
        meeting_points=meetings,
        recommended_commitment=recommended,
        committed_points=total,
        stretch=stretch,
        recommended=rec,
        notes=notes,
    )

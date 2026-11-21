"""Delegation: workload, ranked candidates, rebalance plans and stalled-item nudges."""

from __future__ import annotations

import uuid
from collections import Counter
from datetime import timedelta
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from twinpm.core.tenancy import TenantContext
from twinpm.db import models as m
from twinpm.db.repository import Repo
from twinpm.domain import OVERLOAD_THRESHOLD, capacity_points
from twinpm.ml import forecast, scenario
from twinpm.ml.delegation import Ranker, bounded_weights, plan_rebalance, required_skills
from twinpm.ml.features import FeatureBuilder
from twinpm.schemas.delegation import (
    CandidateOut,
    CandidatesOut,
    NudgeRunOut,
    PersonLoad,
    RebalanceMove,
    RebalanceOut,
    WorkloadOut,
)
from twinpm.services import ml_jobs, suggestions
from twinpm.services.data_cache import get_program_data

STALL_DAYS = 3.0
REVIEW_WAIT_HOURS = 24.0


async def learned_weights(session: AsyncSession, ctx: TenantContext) -> dict[str, float]:
    persona = (
        await session.execute(
            select(m.PersonaProfile).where(
                m.PersonaProfile.org_id == ctx.org_id, m.PersonaProfile.user_id == ctx.user_id
            )
        )
    ).scalar_one_or_none()
    return bounded_weights(persona.delegation_weights if persona else None)


async def workload(session: AsyncSession, ctx: TenantContext, program_id: uuid.UUID) -> WorkloadOut:
    data = await get_program_data(session, ctx.org_id, program_id)
    fb = FeatureBuilder(data)
    now = pd.Timestamp(data.now)
    skills = data.skills.set_index("id")["name"].to_dict()
    teams = data.teams.set_index("id")["name"].to_dict()
    week_starts = [(now.normalize() + pd.Timedelta(days=7 * k)) for k in range(-4, 4)]
    it = data.items
    people = []
    for p in data.people[data.people["team_id"].notna()].itertuples():
        cap = capacity_points(float(p.capacity_hours_per_week))
        mine = it[(it["assignee_person_id"] == p.id) & (it["status"] != "done")]
        weeks = []
        for ws in week_starts:
            if ws <= now:
                u = fb.utilisation(p.id, ws + pd.Timedelta(days=3))
            else:
                # Forward weeks: open work spread to due dates against half-sprint capacity.
                due = mine[
                    (pd.to_datetime(mine["due_date"]).dt.tz_localize("UTC") >= ws)
                    & (
                        pd.to_datetime(mine["due_date"]).dt.tz_localize("UTC")
                        < ws + pd.Timedelta(days=7)
                    )
                ]
                u = float(due["story_points"].sum()) / (cap / 2)
            weeks.append({"week": ws.date().isoformat(), "utilisation": round(u, 3)})
        util = fb.utilisation(p.id, now)
        people.append(
            PersonLoad(
                person_id=p.id,
                name=p.name,
                title=p.title,
                team_id=p.team_id,
                team=teams.get(p.team_id),
                utilisation=round(util, 3),
                assigned_points=float(mine["story_points"].sum()),
                capacity_points=cap,
                overloaded=util > OVERLOAD_THRESHOLD,
                skills={
                    skills[r.skill_id]: int(r.level)
                    for r in data.person_skills.itertuples()
                    if r.person_id == p.id
                },
                growth_goals=list(p.growth_goals or []),
                weeks=weeks,
            )
        )
    recent = it[it["created_at_src"] > now - timedelta(days=90)]
    names = data.people.set_index("id")["name"].to_dict()
    counts = Counter(names.get(a) for a in recent["assignee_person_id"].dropna())
    return WorkloadOut(
        people=people,
        weeks=[w.date().isoformat() for w in week_starts],
        overload_threshold=OVERLOAD_THRESHOLD,
        assignment_counts={k: v for k, v in counts.items() if k},
    )


async def candidates(
    session: AsyncSession, ctx: TenantContext, work_item_id: uuid.UUID
) -> CandidatesOut:
    item_row = await Repo(session, ctx, m.WorkItem).get(work_item_id)
    program, _ = await ml_jobs.program_context(session, ctx.org_id)
    data = await get_program_data(session, ctx.org_id, program.id)
    item = data.items.set_index("id", drop=False).loc[item_row.id]
    weights = await learned_weights(session, ctx)
    ranker = Ranker(data, weights)
    epic = data.epics.set_index("id")["title"].get(item["epic_id"], "")
    return CandidatesOut(
        work_item_id=item_row.id,
        key=item_row.key,
        title=item_row.title,
        required_skills=required_skills(f"{item['title']} {epic}", list(item["labels"] or [])),
        weights=weights,
        candidates=[
            CandidateOut(
                person_id=c.person_id,
                name=c.name,
                team_id=c.team_id,
                score=c.score,
                factors=c.factors,
                explanation=c.explanation,
                utilisation=c.utilisation,
            )
            for c in ranker.rank(item)
        ],
    )


async def rebalance(
    session: AsyncSession,
    ctx: TenantContext,
    program_id: uuid.UUID,
    scope: list[uuid.UUID] | None = None,
) -> RebalanceOut:
    _, milestone = await ml_jobs.program_context(session, ctx.org_id)
    data = await get_program_data(session, ctx.org_id, program_id)
    risks = await ml_jobs.latest_risks(session, ctx.org_id)
    dm, _ = ml_jobs.get_models()
    inp = forecast.build_input(data, milestone.id, risks)
    crit = set(scope) if scope else forecast.critical_epics(data, inp)
    moves = plan_rebalance(data, risks, crit, await learned_weights(session, ctx))
    changes = [
        {
            "type": "reassign",
            "work_item_ids": [str(mv.work_item_id)],
            "to_person_id": str(mv.to_person_id),
        }
        for mv in moves
    ]
    res = scenario.run(data, inp, changes, dm)
    plan_id = uuid.uuid4()
    names = data.people.set_index("id")["name"].to_dict()
    out_moves = []
    for mv in moves:
        frm = names.get(mv.from_person_id) if pd.notna(mv.from_person_id) else None
        cites = [
            {"type": "work_item", "id": str(mv.work_item_id), "label": mv.key},
            {"type": "person", "id": str(mv.to_person_id), "label": mv.to_name},
        ]
        s = await suggestions.create(
            session,
            ctx,
            type="reassign",
            agent="delegation",
            title=f"Reassign {mv.key} to {mv.to_name}" + (f" (from {frm})" if frm else ""),
            payload={
                "work_item_ids": [str(mv.work_item_id)],
                "to_person_id": str(mv.to_person_id),
                "reason": f"Rebalance plan {plan_id}",
                "plan_id": str(plan_id),
                "factors": mv.candidate.factors,
                "risk": mv.risk,
            },
            explanation=mv.candidate.explanation,
            drivers=[
                {"feature": k, "value": v, "contribution": v, "label": k.replace("_", " ")}
                for k, v in mv.candidate.factors.items()
                if v
            ],
            citations=cites,
            program_id=program_id,
        )
        out_moves.append(
            RebalanceMove(
                work_item_id=mv.work_item_id,
                key=mv.key,
                title=mv.title,
                from_person_id=mv.from_person_id if pd.notna(mv.from_person_id) else None,
                from_name=frm,
                to_person_id=mv.to_person_id,
                to_name=mv.to_name,
                points=mv.points,
                risk=mv.risk,
                explanation=mv.candidate.explanation,
                factors=mv.candidate.factors,
                suggestion_id=s.id if s else None,
            )
        )
    return RebalanceOut(
        plan_id=plan_id,
        moves=out_moves,
        baseline_p80=res.baseline.p80.isoformat(),
        scenario_p80=res.scenario.p80.isoformat(),
        delta_days=res.delta_days,
        narrative=res.narrative,
    )


def stalled_items(data: Any) -> list[dict[str, Any]]:
    fb = FeatureBuilder(data)
    now = pd.Timestamp(data.now)
    out = []
    for r in data.items[
        data.items["status"].isin(["in_progress", "in_review", "blocked"])
    ].itertuples():
        status, since = fb.status_at(r.id, now)
        days = (now - (since or r.created_at_src)).total_seconds() / 86400
        review = fb.review_hours_at(r.id, now)
        open_pr = (
            any(e.kind == "pr_opened" for e in fb.events.get(r.id, ())) and status == "in_review"
        )
        if days >= STALL_DAYS or (open_pr and review >= REVIEW_WAIT_HOURS):
            out.append(
                {
                    "id": r.id,
                    "key": r.key,
                    "title": r.title,
                    "status": status,
                    "days": round(days, 1),
                    "review_hours": round(review, 1),
                    "assignee": r.assignee_person_id,
                    "team_id": r.team_id,
                }
            )
    return out


async def run_nudges(
    session: AsyncSession, ctx: TenantContext, program_id: uuid.UUID
) -> NudgeRunOut:
    data = await get_program_data(session, ctx.org_id, program_id)
    stalled = stalled_items(data)
    names = data.people.set_index("id")["name"].to_dict()
    created = auto = 0
    since = pd.Timestamp(data.now) - timedelta(days=2)
    recent_titles = set(
        (
            await session.execute(
                select(m.Suggestion.title).where(
                    m.Suggestion.org_id == ctx.org_id,
                    m.Suggestion.type == "nudge",
                    m.Suggestion.created_at > since.to_pydatetime(),
                )
            )
        ).scalars()
    )
    for s in stalled[:10]:
        if s["assignee"] is None or pd.isna(s["assignee"]):
            continue
        who = names.get(s["assignee"], "there")
        title = f"Follow up with {who} on {s['key']}"
        if title in recent_titles:
            continue
        reason = (
            f"PR waiting {s['review_hours']:.0f}h for review"
            if s["status"] == "in_review"
            else f"{s['days']:.0f} days in {s['status'].replace('_', ' ')}"
        )
        sug = await suggestions.create(
            session,
            ctx,
            type="nudge",
            agent="delegation",
            title=title,
            payload={
                "work_item_id": str(s["id"]),
                "person_id": str(s["assignee"]),
                "message": f"Hi {who.split()[0]}, quick check on {s['key']} "
                f"({s['title']}): {reason}. Anything blocking you that I can "
                "help unblock?",
            },
            explanation=f"{s['key']} looks stalled: {reason}.",
            citations=[{"type": "work_item", "id": str(s["id"]), "label": s["key"]}],
            program_id=program_id,
        )
        if sug is not None:
            created += 1
            auto += int(sug.status == "auto_executed")
    return NudgeRunOut(stalled=len(stalled), suggestions_created=created, auto_executed=auto)

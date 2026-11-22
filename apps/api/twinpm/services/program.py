"""Command Center: program health, morning briefing and the activity feed."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from twinpm.core.redis import get_redis
from twinpm.core.tenancy import TenantContext
from twinpm.db import models as m
from twinpm.db.repository import Repo
from twinpm.graph.dependency import build as build_graph
from twinpm.ml import forecast, preference, scenario
from twinpm.ml.delegation import plan_rebalance
from twinpm.schemas.common import Citation, Driver
from twinpm.schemas.program import (
    ActivityItem,
    BriefingItem,
    BriefingOut,
    HealthDriver,
    HealthOut,
    RecommendedAction,
    TrendPoint,
)
from twinpm.services import ml_jobs, suggestions
from twinpm.services.data_cache import get_program_data

SEVERITY_WEIGHT = {"critical": 4.0, "high": 3.0, "medium": 2.0, "low": 1.0}
BRIEFING_TTL = 6 * 3600


async def get_program(
    session: AsyncSession, ctx: TenantContext, program_id: uuid.UUID
) -> m.Program:
    return await Repo(session, ctx, m.Program).get(program_id)


async def health(session: AsyncSession, ctx: TenantContext, program_id: uuid.UUID) -> HealthOut:
    await get_program(session, ctx, program_id)
    snaps = (
        (
            await session.execute(
                select(m.HealthSnapshot)
                .where(
                    m.HealthSnapshot.org_id == ctx.org_id, m.HealthSnapshot.program_id == program_id
                )
                .order_by(m.HealthSnapshot.date.desc())
                .limit(45)
            )
        )
        .scalars()
        .all()
    )
    if not snaps:
        await ml_jobs.refresh_org(session, ctx.org_id)
        return await health(session, ctx, program_id)
    latest = snaps[0]
    week_ago = next((s for s in snaps if s.date <= latest.date - timedelta(days=7)), None)
    return HealthOut(
        score=latest.score,
        delta_7d=round(latest.score - week_ago.score, 1) if week_ago else None,
        subscores=latest.subscores,
        trend=[TrendPoint(date=s.date, score=s.score) for s in reversed(snaps[:30])],
        drivers=[HealthDriver(**d) for d in latest.drivers],
        computed_at=latest.date,
    )


async def forecasts(
    session: AsyncSession, milestone_id: uuid.UUID
) -> tuple[m.Forecast | None, m.Forecast | None]:
    rows = (
        (
            await session.execute(
                select(m.Forecast)
                .where(m.Forecast.milestone_id == milestone_id)
                .order_by(m.Forecast.run_at.desc())
                .limit(200)
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return None, None
    latest = rows[0]
    previous = next((r for r in rows if r.run_at <= latest.run_at - timedelta(days=13)), None)
    return latest, previous


def _cite(type_: str, id_: Any, label: str) -> Citation:
    return Citation(type=type_, id=str(id_), label=label)


async def _scenario_options(
    session: AsyncSession,
    ctx: TenantContext,
    data: Any,
    milestone: m.Milestone,
    risks: dict[Any, float],
    epic_id: Any,
) -> tuple[list[dict[str, Any]], Any]:
    from twinpm.services.ml_jobs import get_models

    dm, _ = get_models()
    inp = forecast.build_input(data, milestone.id, risks)
    base = forecast.simulate(inp)
    moves = plan_rebalance(data, risks, forecast.critical_epics(data, inp))
    rebalance = [
        {
            "type": "reassign",
            "work_item_ids": [str(mv.work_item_id)],
            "to_person_id": str(mv.to_person_id),
        }
        for mv in moves
    ]
    epic_items = inp.items[inp.items["epic_id"] == epic_id].sort_values("risk")
    n_cut = max(1, len(epic_items) // 5)
    descope = [
        {"type": "remove_scope", "work_item_ids": [str(w) for w in epic_items.head(n_cut)["id"]]}
    ]
    shift = max(0, (base.p80 - milestone.target_date).days)
    options = []
    people = data.people.set_index("id")["name"].to_dict()
    for name, changes, desc in (
        (
            "Rebalance",
            rebalance,
            "Move critical-path work to "
            + ", ".join(sorted({people.get(mv.to_person_id, "?") for mv in moves})),
        ),
        ("Descope", descope, f"Defer the {n_cut} lowest-risk Payments API items"),
        (
            "Move the date",
            [{"type": "date_shift", "days": shift}],
            f"Shift the launch target by {shift} days",
        ),
    ):
        res = scenario.run(data, inp, changes, dm, baseline=base)
        target = milestone.target_date + timedelta(days=shift if name == "Move the date" else 0)
        options.append(
            {
                "name": name,
                "description": desc,
                "changes": changes,
                "p80": res.scenario.p80.isoformat(),
                "delta_days": res.delta_days,
                "days_vs_target": (res.scenario.p80 - target).days,
                "risk_delta": res.risk_delta,
                "narrative": res.narrative,
                "moves": [
                    {
                        "work_item_id": str(mv.work_item_id),
                        "key": mv.key,
                        "to_person_id": str(mv.to_person_id),
                        "to_name": mv.to_name,
                        "from_name": people.get(mv.from_person_id),
                        "explanation": mv.candidate.explanation,
                        "factors": mv.candidate.factors,
                    }
                    for mv in moves
                ]
                if name == "Rebalance"
                else [],
            }
        )
    return options, base


async def _accept_probabilities(
    session: AsyncSession, ctx: TenantContext
) -> preference.PreferenceModel:
    rows = (
        (
            await session.execute(
                select(m.PreferenceEvent).where(m.PreferenceEvent.org_id == ctx.org_id)
            )
        )
        .scalars()
        .all()
    )
    ev = pd.DataFrame(
        [
            {
                "user_id": r.user_id,
                "suggestion_type": r.suggestion_type,
                "context_features": r.context_features,
                "outcome": r.outcome,
            }
            for r in rows
        ]
    )
    return preference.fit(ev, ctx.user_id)


async def build_briefing(
    session: AsyncSession, ctx: TenantContext, program_id: uuid.UUID
) -> BriefingOut:
    program = await get_program(session, ctx, program_id)
    _, milestone = await ml_jobs.program_context(session, ctx.org_id)
    data = await get_program_data(session, ctx.org_id, program_id)
    preds = (
        (
            await session.execute(
                select(m.MlPrediction).where(
                    m.MlPrediction.org_id == ctx.org_id, m.MlPrediction.model_name == "delay_risk"
                )
            )
        )
        .scalars()
        .all()
    )
    risks = {p.entity_id: p.score for p in preds}
    drivers_by_item = {p.entity_id: p.drivers for p in preds}
    latest, previous = await forecasts(session, milestone.id)
    epics = data.epics.set_index("id")
    it = data.items
    items: list[dict[str, Any]] = []
    owner = await session.get(m.User, program.owner_user_id) if program.owner_user_id else None
    twin_name = f"{owner.name.split()[0]}'s twin" if owner else "Your twin"

    # 1. Critical-path slip.
    scope = {uuid.UUID(str(e)) for e in milestone.scope}
    graph = build_graph(data, risks, scope)
    crit = [n for n in graph.critical_path if graph.graph.nodes[n]["kind"] == "epic"]
    if crit and latest is not None:
        epic_id = max(crit, key=lambda n: graph.graph.nodes[n]["risk"])
        epic = epics.loc[epic_id]
        dependents = [
            d
            for d in graph.graph.successors(epic_id)
            if graph.graph.nodes[d]["kind"] == "epic"
        ]
        epic_p80 = date.fromisoformat(
            latest.distribution["epic_p80"].get(str(epic_id), latest.p80_date.isoformat())
        )
        slip = (epic_p80 - epic["target_date"]).days if pd.notna(epic["target_date"]) else 0
        open_items = it[(it["epic_id"] == epic_id) & (it["status"] != "done")]
        top_items = sorted(open_items["id"], key=lambda w: -risks.get(w, 0))[:3]
        agg: dict[str, Driver] = {}
        for w in top_items:
            for d in drivers_by_item.get(w, []):
                if d["feature"] not in agg or d["contribution"] > agg[d["feature"]].contribution:
                    agg[d["feature"]] = Driver(**d)
        drivers = sorted(agg.values(), key=lambda d: -d.contribution)[:3]
        reopened = int((open_items["reopen_count"] > 0).sum())
        prev_txt = (
            f"Launch P80 moves from {previous.p80_date:%b %d} to {latest.p80_date:%b %d}"
            if previous
            else f"Launch P80 is {latest.p80_date:%b %d}"
        )
        title = (
            f"{epic['title']} likely to slip ~{max(slip, 0)} days; {len(dependents)} launch "
            f"epics depend on it. {prev_txt}."
        )
        options, base = await _scenario_options(session, ctx, data, milestone, risks, epic_id)
        drv_txt = "; ".join(d.label for d in drivers) or "high model risk on in-flight items"
        why = (
            f"The delay model puts {len(top_items)} in-flight {epic['title']} items above "
            f"{min(risks.get(w, 0) for w in top_items):.0%} ({drv_txt}). {reopened} item"
            f"{'s were' if reopened != 1 else ' was'} reopened after review. It sits on the "
            f"critical path, so {', '.join(graph.graph.nodes[d]['label'] for d in dependents[:3])}"
            f" wait on it."
        )
        citations = [_cite("epic", epic_id, epic["title"])]
        citations += [
            _cite("work_item", w, str(it.set_index("id").at[w, "key"])) for w in top_items
        ]
        citations.append(_cite("forecast", latest.id, f"Launch forecast {latest.run_at:%b %d}"))
        sug = await _ensure_suggestion(
            session,
            ctx,
            program_id,
            "scenario",
            f"Options for the {epic['title']} slip",
            {
                "name": f"{epic['title']} slip options",
                "changes": options[0]["changes"],
                "options": options,
                "result": {"baseline_p80": base.p80.isoformat()},
            },
            "planner",
            why,
            [d.model_dump() for d in drivers],
            [c.model_dump() for c in citations],
        )
        items.append(
            {
                "kind": "critical_path_slip",
                "title": title,
                "why": why,
                "severity": "critical" if slip > 5 else "high",
                "drivers": drivers,
                "evidence": citations,
                "type": "scenario",
                "action": RecommendedAction(
                    suggestion_id=sug.id if sug else None, label="See options", href="/roadmap"
                ),
            }
        )

    # 2. Overloaded people.
    from twinpm.ml.features import FeatureBuilder

    fb = FeatureBuilder(data)
    now = pd.Timestamp(data.now)
    team_people = data.people[data.people["team_id"].notna()]
    loads = sorted(
        ((fb.utilisation(p.id, now), p) for p in team_people.itertuples()), key=lambda x: -x[0]
    )
    if loads and loads[0][0] > 1.0:
        util, person = loads[0]
        prev_sprint = fb.utilisation(person.id, now - pd.Timedelta(days=14))
        spare = [p.name.split()[0] for u, p in loads[::-1][:2] if u < 0.7]
        items.append(
            {
                "kind": "overload",
                "severity": "high",
                "title": f"{person.name} is at {util:.0%} utilisation"
                + (" for the second sprint running" if prev_sprint > 0.9 else ""),
                "why": f"{person.name} carries {util:.0%} of sprint capacity "
                f"(last sprint {prev_sprint:.0%}). {' and '.join(spare)} have the most "
                "headroom. Sustained overload drives the review backlog and reopen rate.",
                "drivers": [
                    Driver(
                        feature="assignee_utilisation",
                        value=round(util, 3),
                        contribution=round(util - 0.85, 3),
                        label=f"{person.name.split()[0]} at {util:.0%} utilisation",
                    )
                ],
                "evidence": [_cite("person", person.id, person.name)],
                "type": "reassign",
                "action": RecommendedAction(
                    suggestion_id=None, label="Rebalance workload", href="/delegation"
                ),
            }
        )

    # 3. Anomalies.
    anomalies = (
        (
            await session.execute(
                select(m.Anomaly)
                .where(m.Anomaly.org_id == ctx.org_id, m.Anomaly.status == "open")
                .order_by(m.Anomaly.z_score.desc())
            )
        )
        .scalars()
        .all()
    )
    review = next((a for a in anomalies if a.metric == "review_latency_p50"), None)
    top_anom = review or (anomalies[0] if anomalies else None)
    if top_anom is not None:
        items.append(
            {
                "kind": "anomaly",
                "severity": "medium",
                "title": top_anom.explanation.split(",")[0],
                "why": top_anom.explanation,
                "type": "nudge",
                "drivers": [
                    Driver(
                        feature=top_anom.metric,
                        value=top_anom.value,
                        contribution=round(abs(top_anom.z_score) / 10, 3),
                        label=f"z = {top_anom.z_score:+.1f} ({top_anom.method})",
                    )
                ],
                "evidence": [_cite("anomaly", top_anom.id, top_anom.metric.replace("_", " "))],
                "action": RecommendedAction(
                    suggestion_id=None, label="Nudge reviewers", href="/delegation"
                ),
            }
        )

    # 4. Top customer theme.
    theme = (
        (await session.execute(select(m.Theme).where(m.Theme.org_id == ctx.org_id).limit(50)))
        .scalars()
        .all()
    )
    if theme:
        t = max(theme, key=lambda x: float(x.opportunity_score.get("score", 0)))
        items.append(
            {
                "kind": "opportunity",
                "severity": "low",
                "type": "create_task",
                "title": f"'{t.label}' is the top customer opportunity ({t.size} requests)",
                "why": f"{t.summary} Opportunity score {t.opportunity_score.get('score')}.",
                "drivers": [
                    Driver(feature=k, value=v, contribution=round(v * w, 3), label=k)
                    for k, v in t.opportunity_score.get("breakdown", {}).items()
                    for w in [t.opportunity_score.get("weights", {}).get(k, 0)]
                ][:3],
                "evidence": [_cite("theme", t.id, t.label)],
                "action": RecommendedAction(
                    suggestion_id=None, label="Draft PRD", href="/strategy"
                ),
            }
        )

    pm = await _accept_probabilities(session, ctx)
    for x in items:
        x["p"] = pm.accept_probability(
            preference.context_features(x["type"], 3, len(x["drivers"]), len(x["evidence"]), 0.5)
        )
        x["rank_score"] = SEVERITY_WEIGHT[x["severity"]] * (0.5 + x["p"])
    items.sort(key=lambda x: -x["rank_score"])
    return BriefingOut(
        generated_at=datetime.now(UTC),
        drafted_by=twin_name,
        items=[
            BriefingItem(
                rank=i + 1,
                kind=x["kind"],
                title=x["title"],
                why=x["why"],
                severity=x["severity"],
                drivers=x["drivers"],
                evidence=x["evidence"],
                recommended_action=x["action"],
                accept_probability=round(x["p"], 3),
            )
            for i, x in enumerate(items[:3])
        ],
    )


async def _ensure_suggestion(
    session: AsyncSession,
    ctx: TenantContext,
    program_id: uuid.UUID,
    type_: str,
    title: str,
    payload: dict[str, Any],
    agent: str,
    explanation: str,
    drivers: list[dict[str, Any]],
    citations: list[dict[str, Any]],
) -> m.Suggestion | None:
    """Reuse today's pending suggestion with the same title instead of piling up copies."""
    since = datetime.now(UTC) - timedelta(hours=20)
    existing = (
        (
            await session.execute(
                select(m.Suggestion).where(
                    m.Suggestion.org_id == ctx.org_id,
                    m.Suggestion.title == title,
                    m.Suggestion.status == "pending",
                    m.Suggestion.created_at > since,
                )
            )
        )
        .scalars()
        .first()
    )
    if existing is not None:
        existing.payload = payload
        return existing
    return await suggestions.create(
        session,
        ctx,
        type=type_,
        title=title,
        payload=payload,
        agent=agent,
        explanation=explanation,
        drivers=drivers,
        citations=citations,
        program_id=program_id,
    )


def _cache_key(org_id: uuid.UUID, program_id: uuid.UUID) -> str:
    return f"twinpm:briefing:{org_id}:{program_id}:{datetime.now(UTC).date()}"


async def briefing(
    session: AsyncSession, ctx: TenantContext, program_id: uuid.UUID, refresh: bool = False
) -> BriefingOut:
    key = _cache_key(ctx.org_id, program_id)
    r = get_redis()
    if not refresh:
        cached = await r.get(key)
        if cached:
            return BriefingOut.model_validate(json.loads(cached))
    out = await build_briefing(session, ctx, program_id)
    await r.set(key, out.model_dump_json(), ex=BRIEFING_TTL)
    return out


async def invalidate_briefing(org_id: uuid.UUID, program_id: uuid.UUID) -> None:
    await get_redis().delete(_cache_key(org_id, program_id))


SUMMARY = {
    "work_item.reassigned": "reassigned a work item",
    "work_item.reassign_undone": "undid a reassignment",
    "work_item.created": "created a work item",
    "suggestion.created": "proposed an action",
    "suggestion.accepted": "approved a suggestion",
    "suggestion.edited": "edited and approved a suggestion",
    "suggestion.rejected": "rejected a suggestion",
    "risk.created": "added a risk",
    "risk.updated": "updated a risk",
    "status_report.sent": "sent a status report",
    "nudge.sent": "sent a follow-up",
    "initiative.updated": "changed the roadmap",
    "scenario.saved": "saved a scenario",
    "twin.observed": "noticed something",
}


async def activity(
    session: AsyncSession, ctx: TenantContext, limit: int = 50
) -> list[ActivityItem]:
    from twinpm.services import audit

    rows = await audit.query(session, ctx, limit=limit)
    users = {
        u.id: u.name
        for u in (
            await session.execute(select(m.User).where(m.User.org_id == ctx.org_id))
        ).scalars()
    }
    out = []
    for r in rows:
        name = users.get(r.actor_id) if r.actor_id else None
        who = (
            f"{name.split()[0]}'s twin"
            if r.actor_type == "twin" and name
            else (name or r.actor_type.title())
        )
        title = (r.after or {}).get("title") or (r.after or {}).get("key") or ""
        out.append(
            ActivityItem(
                id=r.id,
                actor_type=r.actor_type,
                actor_id=r.actor_id,
                actor_name=who,
                action=r.action,
                entity_type=r.entity_type,
                entity_id=r.entity_id,
                summary=f"{who} {SUMMARY.get(r.action, r.action.replace('.', ' '))}"
                + (f": {title}" if title else ""),
                reason=r.reason,
                suggestion_id=r.suggestion_id,
                occurred_at=r.occurred_at,
            )
        )
    return out

"""Risk radar: at-risk items, the risk register, the dependency graph and slip impact."""

from __future__ import annotations

import uuid
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from twinpm.core.tenancy import TenantContext
from twinpm.db import models as m
from twinpm.db.repository import Repo
from twinpm.graph.dependency import build as build_graph
from twinpm.graph.dependency import downstream
from twinpm.ml import forecast
from twinpm.ml.features import FeatureBuilder
from twinpm.schemas.common import Driver
from twinpm.schemas.risk import GraphEdge, GraphNode, GraphOut, ImpactOut, RiskyItem
from twinpm.services import actions, ml_jobs
from twinpm.services.data_cache import get_program_data


async def risky_items(
    session: AsyncSession,
    ctx: TenantContext,
    program_id: uuid.UUID,
    min_score: float = 0.0,
    limit: int = 100,
) -> list[RiskyItem]:
    await Repo(session, ctx, m.Program).get(program_id)
    rows = (
        await session.execute(
            select(m.MlPrediction, m.WorkItem)
            .join(m.WorkItem, m.WorkItem.id == m.MlPrediction.entity_id)
            .where(
                m.MlPrediction.org_id == ctx.org_id,
                m.MlPrediction.model_name == "delay_risk",
                m.MlPrediction.score >= min_score,
                m.WorkItem.deleted_at.is_(None),
                m.WorkItem.status != "done",
            )
            .order_by(m.MlPrediction.score.desc())
            .limit(limit)
        )
    ).all()
    if ctx.role == "member" and ctx.person_id is not None:
        rows = [r for r in rows if r[1].assignee_person_id == ctx.person_id]
    people = {p.id: p.name for p in await Repo(session, ctx, m.Person).all()}
    epics = {e.id: e.title for e in await Repo(session, ctx, m.Epic).all()}
    teams = {t.id: t.name for t in await Repo(session, ctx, m.Team).all()}
    return [
        RiskyItem(
            work_item_id=w.id,
            key=w.key,
            title=w.title,
            epic=epics.get(w.epic_id) if w.epic_id else None,
            team=teams.get(w.team_id) if w.team_id else None,
            status=w.status,
            owner=people.get(w.assignee_person_id) if w.assignee_person_id else None,
            owner_id=w.assignee_person_id,
            due_date=w.due_date,
            probability=p.score,
            drivers=[Driver(**d) for d in p.drivers],
            model_version=p.model_version,
        )
        for p, w in rows
    ]


async def create_risk(session: AsyncSession, ctx: TenantContext, body: dict[str, Any]) -> m.Risk:
    body = {
        k: (str(v) if isinstance(v, uuid.UUID) else v) for k, v in body.items() if k != "program_id"
    }
    out = await actions.execute(session, ctx, "risk_update", body)
    return await Repo(session, ctx, m.Risk).get(uuid.UUID(out["risk_id"]))


async def update_risk(
    session: AsyncSession, ctx: TenantContext, risk_id: uuid.UUID, changes: dict[str, Any]
) -> m.Risk:
    await Repo(session, ctx, m.Risk).get(risk_id)
    payload = {
        "risk_id": str(risk_id),
        **{k: (str(v) if isinstance(v, uuid.UUID) else v) for k, v in changes.items()},
    }
    await actions.execute(session, ctx, "risk_update", payload)
    return await Repo(session, ctx, m.Risk).get(risk_id)


async def dependency_graph(
    session: AsyncSession, ctx: TenantContext, program_id: uuid.UUID
) -> GraphOut:
    _, milestone = await ml_jobs.program_context(session, ctx.org_id)
    data = await get_program_data(session, ctx.org_id, program_id)
    risks = await ml_jobs.latest_risks(session, ctx.org_id)
    scope = {uuid.UUID(str(e)) for e in milestone.scope}
    # Include epics outside launch scope that touch it through dependencies.
    deps = data.deps
    extra = set(deps.loc[deps["to_id"].isin(scope) & (deps["from_type"] == "epic"), "from_id"])
    res = build_graph(data, risks, scope | extra)
    g = res.graph
    crit = set(res.critical_path)
    nodes = [
        GraphNode(
            id=n,
            kind=a["kind"],
            label=a["label"],
            key=a.get("key"),
            team_id=a.get("team_id"),
            team=a.get("team"),
            status=a["status"],
            risk=a["risk"],
            scope_points=a["scope_points"],
            open_items=a["open_items"],
            duration_days=a["duration"],
            slack_days=a.get("slack", 0.0),
            critical=bool(a["critical"]),
            epic_id=a.get("epic_id"),
        )
        for n, a in g.nodes(data=True)
    ]
    edges = [
        GraphEdge(
            source=u,
            target=v,
            kind=a["kind"],
            status=a["status"],
            level=a["level"],
            critical=(u in crit and v in crit)
            or (g.nodes[u]["critical"] and g.nodes[v]["critical"]),
        )
        for u, v, a in g.edges(data=True)
    ]
    return GraphOut(
        nodes=nodes, edges=edges, critical_path=res.critical_path, finish_days=res.finish_days
    )


async def impact(
    session: AsyncSession, ctx: TenantContext, entity_id: uuid.UUID, slip_days: int
) -> ImpactOut:
    program, milestone = await ml_jobs.program_context(session, ctx.org_id)
    data = await get_program_data(session, ctx.org_id, program.id)
    risks = await ml_jobs.latest_risks(session, ctx.org_id)
    scope = {uuid.UUID(str(e)) for e in milestone.scope}
    g = build_graph(data, risks, scope).graph
    if entity_id not in g:
        epic_of = data.items.set_index("id")["epic_id"].to_dict()
        if entity_id not in epic_of:
            await Repo(session, ctx, m.Epic).get(entity_id)  # raises 404 for unknown ids
        node = epic_of.get(entity_id, entity_id)
    else:
        node = entity_id
    affected_ids = downstream(g, node) if node in g else []
    inp = forecast.build_input(data, milestone.id, risks)
    base = forecast.simulate(inp)
    # A slip of N days on an entity = N days of its team's program throughput as extra work.
    attrs = g.nodes.get(node, {})
    team = attrs.get("team_id")
    fb = FeatureBuilder(data)
    v = fb.sprint_velocities(team, pd.Timestamp(data.now), 6) if team else []
    from twinpm.domain import PROGRAM_ALLOCATION, SPRINT_DAYS

    daily = (sum(v) / len(v) if v else 20.0) * PROGRAM_ALLOCATION / SPRINT_DAYS
    epic_id = node if attrs.get("kind") == "epic" else attrs.get("epic_id", node)
    slipped = forecast.ForecastInput(
        items=pd.concat(
            [
                inp.items,
                pd.DataFrame(
                    [
                        {
                            "id": uuid.uuid4(),
                            "key": "SLIP",
                            "team_id": team,
                            "epic_id": epic_id,
                            "assignee": None,
                            "points": daily * slip_days,
                            "risk": 0.0,
                            "gate_epic": None,
                        }
                    ]
                ),
            ],
            ignore_index=True,
        ),
        throughput=inp.throughput,
        capacity_factor=inp.capacity_factor,
        gating_epics=inp.gating_epics | {epic_id},
        start=inp.start,
        target=inp.target,
    )
    res = forecast.simulate(slipped)
    delta = (res.p80 - base.p80).days
    label = attrs.get("label", str(entity_id))
    affected = [
        {
            "id": str(a),
            "label": g.nodes[a]["label"],
            "kind": g.nodes[a]["kind"],
            "team": g.nodes[a].get("team"),
        }
        for a in affected_ids
    ]
    epics_hit = [a["label"] for a in affected if a["kind"] == "epic"]
    return ImpactOut(
        entity_id=entity_id,
        slip_days=slip_days,
        affected=affected,
        baseline_p80=base.p80,
        new_p80=res.p80,
        delta_days=delta,
        narrative=(
            f"A {slip_days}-day slip on {label} reaches {len(epics_hit)} epics"
            + (f" ({', '.join(epics_hit[:4])})" if epics_hit else "")
            + f" and moves launch P80 by {delta} days to {res.p80:%b %d}."
        ),
    )

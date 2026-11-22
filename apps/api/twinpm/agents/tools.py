"""Agent tools. Each has a Pydantic input schema and returns JSON `{data, citations}`.

Tenant context (org, user, role) comes from the run config (`configurable.ctx`), never from
model arguments. Read tools query freely within the tenant. Write tools never write: they
return a `proposed_action`, which the graph's policy gate turns into a suggestion, an approval
interrupt or an immediate execution, according to the autonomy policy.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Awaitable, Callable
from datetime import date, timedelta
from typing import Any, Literal

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from twinpm.agents.guardrails import fence
from twinpm.core.errors import AppError, NotFoundError
from twinpm.core.tenancy import TenantContext
from twinpm.db import models as m
from twinpm.db.repository import Repo
from twinpm.db.session import get_sessionmaker
from twinpm.ml.anomaly import METRICS
from twinpm.rag import retrieval
from twinpm.services import delegation, insights, ml_jobs, planning, program, risk

MAX_ROWS = 12
ToolFn = Callable[[AsyncSession, TenantContext, Any], Awaitable[dict[str, Any]]]


def cite(type_: str, id_: Any, label: str) -> dict[str, str]:
    return {"type": type_, "id": str(id_), "label": label}


def ctx_from(config: RunnableConfig) -> TenantContext:
    ctx = (config.get("configurable") or {}).get("ctx")
    if not isinstance(ctx, TenantContext):
        raise AppError("Tool called without tenant context")
    return ctx


def make_tool(name: str, description: str, schema: type[BaseModel], fn: ToolFn) -> BaseTool:
    async def run(config: RunnableConfig, **kwargs: Any) -> str:
        ctx = ctx_from(config)
        args = schema(**kwargs)
        try:
            async with get_sessionmaker()() as session:
                out = await fn(session, ctx, args)
                await session.commit()
        except (AppError, NotFoundError) as exc:
            out = {"data": {"error": exc.message}, "citations": []}
        out.setdefault("citations", [])
        return json.dumps(out, default=str)

    return StructuredTool.from_function(
        coroutine=run, name=name, description=description, args_schema=schema
    )


class NoArgs(BaseModel):
    pass


class Query(BaseModel):
    query: str = Field(description="What to look for, in plain words")


class RagArgs(BaseModel):
    query: str = Field(description="Search query")
    doc_types: (
        list[Literal["design_doc", "meeting_notes", "transcript", "prd", "status_report"]] | None
    ) = None


class ItemRef(BaseModel):
    work_item: str = Field(description="Work item key such as PAY-239, or its id")


class EpicRef(BaseModel):
    epic: str = Field(description="Epic title such as 'Payments API v2', or its id")


# --------------------------------------------------------------------------- resolvers
async def _program_ids(session: AsyncSession, ctx: TenantContext) -> tuple[m.Program, m.Milestone]:
    return await ml_jobs.program_context(session, ctx.org_id)


async def _item(session: AsyncSession, ctx: TenantContext, ref: str) -> m.WorkItem:
    repo = Repo(session, ctx, m.WorkItem)
    try:
        return await repo.get(uuid.UUID(ref))
    except ValueError:
        pass
    row = (await session.execute(repo.select(m.WorkItem.key == ref.strip().upper()))).scalar()
    if row is None:
        raise NotFoundError(f"No work item {ref!r}")
    return row


async def _epic(session: AsyncSession, ctx: TenantContext, ref: str) -> m.Epic:
    repo = Repo(session, ctx, m.Epic)
    try:
        return await repo.get(uuid.UUID(ref))
    except ValueError:
        pass
    row = (await session.execute(repo.select(m.Epic.title.ilike(f"%{ref.strip()}%")))).scalar()
    if row is None:
        raise NotFoundError(f"No epic {ref!r}")
    return row


async def _person(session: AsyncSession, ctx: TenantContext, ref: str) -> m.Person:
    repo = Repo(session, ctx, m.Person)
    try:
        return await repo.get(uuid.UUID(ref))
    except ValueError:
        pass
    rows = (await session.execute(repo.select())).scalars().all()
    hit = next((p for p in rows if ref.lower() in p.name.lower()), None)
    if hit is None:
        raise NotFoundError(f"No person {ref!r}")
    return hit


# --------------------------------------------------------------------------- strategy
async def search_feedback(s: AsyncSession, ctx: TenantContext, a: Query) -> dict[str, Any]:
    from twinpm.rag.embedding import embed

    vec = embed([a.query])[0].tolist()
    rows = (
        (
            await s.execute(
                select(m.FeedbackItem)
                .where(m.FeedbackItem.org_id == ctx.org_id)
                .order_by(m.FeedbackItem.embedding.cosine_distance(vec))
                .limit(MAX_ROWS)
            )
        )
        .scalars()
        .all()
    )
    return {
        "data": [
            {
                "id": str(r.id),
                "text": fence(r.text, "customer_feedback"),
                "segment": r.customer_segment,
                "sentiment": r.sentiment,
                "source": r.source,
                "received": r.received_at.date(),
            }
            for r in rows
        ],
        "citations": [cite("feedback", r.id, r.text[:40]) for r in rows[:5]],
    }


async def get_themes(s: AsyncSession, ctx: TenantContext, a: NoArgs) -> dict[str, Any]:
    rows = await Repo(s, ctx, m.Theme).all()
    rows = sorted(rows, key=lambda t: -float(t.opportunity_score.get("score", 0)))
    return {
        "data": [
            {
                "id": str(t.id),
                "label": t.label,
                "size": t.size,
                "avg_sentiment": t.avg_sentiment,
                "keywords": t.keywords,
                "opportunity": t.opportunity_score.get("score"),
                "breakdown": t.opportunity_score.get("breakdown"),
                "quotes": [
                    fence(q, "customer_feedback") for q in t.opportunity_score.get("quotes", [])[:2]
                ],
            }
            for t in rows
        ],
        "citations": [cite("theme", t.id, t.label) for t in rows],
    }


class ThemeRef(BaseModel):
    theme: str = Field(description="Theme label or id")


async def score_opportunity(s: AsyncSession, ctx: TenantContext, a: ThemeRef) -> dict[str, Any]:
    rows = await Repo(s, ctx, m.Theme).all()
    t = next((x for x in rows if str(x.id) == a.theme or a.theme.lower() in x.label.lower()), None)
    if t is None:
        raise NotFoundError(f"No theme {a.theme!r}")
    return {
        "data": {"label": t.label, **t.opportunity_score, "size": t.size},
        "citations": [cite("theme", t.id, t.label)],
    }


async def get_objectives(s: AsyncSession, ctx: TenantContext, a: NoArgs) -> dict[str, Any]:
    rows = await Repo(s, ctx, m.Objective).all()
    return {
        "data": [
            {"id": str(o.id), "title": o.title, "quarter": o.quarter, "key_results": o.key_results}
            for o in rows
        ],
        "citations": [],
    }


async def rag_search(s: AsyncSession, ctx: TenantContext, a: RagArgs) -> dict[str, Any]:
    hits = await retrieval.search(
        s, ctx.org_id, a.query, k=5, doc_types=list(a.doc_types) if a.doc_types else None
    )
    data = retrieval.as_context(hits)
    for d in data:
        d["content"] = fence(d["content"], d["type"])
    return {"data": data, "citations": [cite("document", h.document_id, h.title) for h in hits]}


class DraftArgs(BaseModel):
    kind: Literal["prd", "okrs", "status_report", "meeting_prep"]
    topic: str


async def draft_document(s: AsyncSession, ctx: TenantContext, a: DraftArgs) -> dict[str, Any]:
    sections = {
        "prd": [
            "Problem",
            "Users",
            "Goals",
            "Non-goals",
            "Success metrics",
            "Requirements",
            "Risks",
            "Open questions",
        ],
        "okrs": ["Objective", "Key results", "Initiatives", "Risks"],
        "status_report": ["Status", "Wins", "Risks", "Asks", "Next steps"],
        "meeting_prep": ["Purpose", "Context", "Talking points", "Decisions needed"],
    }[a.kind]
    hits = await retrieval.search(s, ctx.org_id, a.topic, k=3)
    return {
        "data": {
            "kind": a.kind,
            "topic": a.topic,
            "sections": sections,
            "context": [fence(h.content[:600], h.doc_type) for h in hits],
        },
        "citations": [cite("document", h.document_id, h.title) for h in hits],
    }


# --------------------------------------------------------------------------- planner
async def get_epic(s: AsyncSession, ctx: TenantContext, a: EpicRef) -> dict[str, Any]:
    e = await _epic(s, ctx, a.epic)
    items = await Repo(s, ctx, m.WorkItem).all(m.WorkItem.epic_id == e.id)
    open_items = [i for i in items if i.status != "done"]
    return {
        "data": {
            "id": str(e.id),
            "title": e.title,
            "status": e.status,
            "target_date": e.target_date,
            "open_items": len(open_items),
            "open_points": sum(i.story_points for i in open_items),
            "done_items": len(items) - len(open_items),
            "items": [
                {"key": i.key, "title": i.title, "status": i.status, "points": i.story_points}
                for i in open_items[:MAX_ROWS]
            ],
        },
        "citations": [cite("epic", e.id, e.title)],
    }


class EstimateArgs(BaseModel):
    titles: list[str] = Field(min_length=1, max_length=10)


async def estimate_effort(s: AsyncSession, ctx: TenantContext, a: EstimateArgs) -> dict[str, Any]:
    import pandas as pd

    _, em = ml_jobs.get_models()
    rows = pd.DataFrame(
        {
            "story_points": [3.0] * len(a.titles),
            "type": ["story"] * len(a.titles),
            "team_id": [""] * len(a.titles),
            "labels": [[]] * len(a.titles),
        }
    )
    est = em.estimate(rows, a.titles)
    return {
        "data": [{"title": t, **e} for t, e in zip(a.titles, est, strict=True)],
        "citations": [cite("work_item", x["id"], x["key"]) for e in est for x in e["similar"][:1]],
    }


class TeamRef(BaseModel):
    team: str = Field(description="Team name, e.g. Payments")


async def get_capacity(s: AsyncSession, ctx: TenantContext, a: TeamRef) -> dict[str, Any]:
    teams = await Repo(s, ctx, m.Team).all()
    t = next((x for x in teams if a.team.lower() in x.name.lower()), None)
    if t is None:
        raise NotFoundError(f"No team {a.team!r}")
    plan = await planning.sprint_plan(s, ctx, t.id, None)
    return {"data": plan.model_dump(mode="json"), "citations": [cite("team", t.id, t.name)]}


class SimArgs(BaseModel):
    option: Literal["rebalance", "descope", "date_shift", "capacity"] = "rebalance"
    team: str | None = None
    factor: float | None = Field(default=None, gt=0, le=3)


async def compare_options(s: AsyncSession, ctx: TenantContext, a: NoArgs) -> dict[str, Any]:
    """The three standard responses to the current critical-path slip, simulated."""
    prog, _ = await _program_ids(s, ctx)
    b = await program.briefing(s, ctx, prog.id)
    sid = next(
        (i.recommended_action.suggestion_id for i in b.items if i.kind == "critical_path_slip"),
        None,
    )
    if sid is None:
        return {"data": {"options": [], "note": "No critical-path slip right now."}}
    sug = await Repo(s, ctx, m.Suggestion).get(sid)
    opts = sug.payload.get("options", [])
    return {
        "data": {
            "baseline_p80": sug.payload.get("result", {}).get("baseline_p80"),
            "options": [
                {
                    k: o[k]
                    for k in (
                        "name",
                        "description",
                        "p80",
                        "delta_days",
                        "days_vs_target",
                        "risk_delta",
                    )
                }
                for o in opts
            ],
            "options_suggestion_id": str(sid),
        },
        "citations": [cite("suggestion", sid, sug.title), *sug.citations[:3]],
    }


async def simulate_scenario(s: AsyncSession, ctx: TenantContext, a: SimArgs) -> dict[str, Any]:
    if a.option != "capacity":
        out = await compare_options(s, ctx, NoArgs())
        name = {"rebalance": "Rebalance", "descope": "Descope", "date_shift": "Move the date"}
        hit = [o for o in out["data"]["options"] if o["name"] == name[a.option]]
        return {"data": hit[0] if hit else out["data"], "citations": out["citations"]}
    teams = await Repo(s, ctx, m.Team).all()
    t = next((x for x in teams if a.team and a.team.lower() in x.name.lower()), None)
    if t is None:
        raise NotFoundError("capacity option needs a team")
    prog, _ = await _program_ids(s, ctx)
    res = await planning.simulate(
        s,
        ctx,
        prog.id,
        [{"type": "capacity_change", "team_id": str(t.id), "factor": a.factor or 1.2}],
    )
    return {
        "data": {"narrative": res.narrative, "delta_days": res.delta_days, "p80": res.scenario.p80},
        "citations": [cite("team", t.id, t.name)],
    }


async def get_roadmap(s: AsyncSession, ctx: TenantContext, a: NoArgs) -> dict[str, Any]:
    prog, _ = await _program_ids(s, ctx)
    rm = await planning.roadmap(s, ctx, prog.id)
    return {
        "data": {
            b: [
                {
                    "title": c.title,
                    "rice": c.rice.get("score"),
                    "risk": c.risk,
                    "dependencies": c.dependency_count,
                }
                for c in cards
            ]
            for b, cards in rm.buckets.items()
        },
        "citations": [
            cite("initiative", c.id, c.title) for cards in rm.buckets.values() for c in cards
        ][:8],
    }


# --------------------------------------------------------------------------- delegation
async def get_workload(s: AsyncSession, ctx: TenantContext, a: NoArgs) -> dict[str, Any]:
    prog, _ = await _program_ids(s, ctx)
    wl = await delegation.workload(s, ctx, prog.id)
    people = sorted(wl.people, key=lambda p: -p.utilisation)
    return {
        "data": [
            {
                "name": p.name,
                "team": p.team,
                "utilisation": p.utilisation,
                "overloaded": p.overloaded,
                "top_skills": dict(sorted(p.skills.items(), key=lambda kv: -kv[1])[:3]),
                "growth_goals": p.growth_goals,
            }
            for p in people
        ],
        "citations": [cite("person", p.person_id, p.name) for p in people[:3]]
        + [cite("person", p.person_id, p.name) for p in people[-3:]],
    }


async def rank_candidates(s: AsyncSession, ctx: TenantContext, a: ItemRef) -> dict[str, Any]:
    item = await _item(s, ctx, a.work_item)
    out = await delegation.candidates(s, ctx, item.id)
    return {
        "data": {
            "work_item": out.key,
            "required_skills": out.required_skills,
            "candidates": [c.model_dump(mode="json") for c in out.candidates[:4]],
        },
        "citations": [cite("work_item", item.id, item.key)]
        + [cite("person", c.person_id, c.name) for c in out.candidates[:2]],
    }


class ReassignArgs(BaseModel):
    work_items: list[str] = Field(min_length=1, max_length=10, description="Keys or ids")
    to_person: str = Field(description="Person name or id")
    reason: str = ""


async def propose_reassignment(
    s: AsyncSession, ctx: TenantContext, a: ReassignArgs
) -> dict[str, Any]:
    person = await _person(s, ctx, a.to_person)
    items = [await _item(s, ctx, w) for w in a.work_items]
    keys = ", ".join(i.key for i in items)
    return {
        "data": {"proposed": f"Reassign {keys} to {person.name}"},
        "proposed_action": {
            "type": "reassign",
            "agent": "delegation",
            "title": f"Reassign {keys} to {person.name}",
            "payload": {
                "work_item_ids": [str(i.id) for i in items],
                "to_person_id": str(person.id),
                "reason": a.reason,
            },
            "explanation": a.reason,
        },
        "citations": [cite("work_item", i.id, i.key) for i in items]
        + [cite("person", person.id, person.name)],
    }


async def propose_rebalance(s: AsyncSession, ctx: TenantContext, a: NoArgs) -> dict[str, Any]:
    """Plan moves off the critical path and propose each one (does not execute)."""
    from twinpm.ml import forecast
    from twinpm.ml.delegation import plan_rebalance
    from twinpm.services.data_cache import get_program_data

    prog, ms = await _program_ids(s, ctx)
    data = await get_program_data(s, ctx.org_id, prog.id)
    risks = await ml_jobs.latest_risks(s, ctx.org_id)
    inp = forecast.build_input(data, ms.id, risks)
    moves = plan_rebalance(
        data, risks, forecast.critical_epics(data, inp), await delegation.learned_weights(s, ctx)
    )
    names = data.people.set_index("id")["name"].to_dict()
    actions = [
        {
            "type": "reassign",
            "agent": "delegation",
            "title": f"Reassign {mv.key} to {mv.to_name}",
            "payload": {
                "work_item_ids": [str(mv.work_item_id)],
                "to_person_id": str(mv.to_person_id),
                "reason": "Rebalance off the critical path",
                "factors": mv.candidate.factors,
                "risk": mv.risk,
            },
            "explanation": mv.candidate.explanation,
            "drivers": [
                {"feature": k, "value": v, "contribution": v, "label": k}
                for k, v in mv.candidate.factors.items()
                if v
            ],
        }
        for mv in moves
    ]
    return {
        "data": [
            {
                "key": mv.key,
                "from": names.get(mv.from_person_id),
                "to": mv.to_name,
                "points": mv.points,
                "why": mv.candidate.explanation,
            }
            for mv in moves
        ],
        "proposed_actions": actions,
        "citations": [cite("work_item", mv.work_item_id, mv.key) for mv in moves]
        + [cite("person", mv.to_person_id, mv.to_name) for mv in moves],
    }


async def find_stalled_items(s: AsyncSession, ctx: TenantContext, a: NoArgs) -> dict[str, Any]:
    from twinpm.services.data_cache import get_program_data

    prog, _ = await _program_ids(s, ctx)
    data = await get_program_data(s, ctx.org_id, prog.id)
    stalled = delegation.stalled_items(data)[:MAX_ROWS]
    names = data.people.set_index("id")["name"].to_dict()
    return {
        "data": [
            {
                **{k: v for k, v in x.items() if k not in ("id", "assignee", "team_id")},
                "owner": names.get(x["assignee"]),
            }
            for x in stalled
        ],
        "citations": [cite("work_item", x["id"], x["key"]) for x in stalled[:5]],
    }


class NudgeArgs(BaseModel):
    work_item: str
    message: str = Field(min_length=5, max_length=600)


async def propose_nudge(s: AsyncSession, ctx: TenantContext, a: NudgeArgs) -> dict[str, Any]:
    item = await _item(s, ctx, a.work_item)
    if item.assignee_person_id is None:
        raise AppError(f"{item.key} has no owner to nudge")
    person = await Repo(s, ctx, m.Person).get(item.assignee_person_id)
    return {
        "data": {"proposed": f"Nudge {person.name} on {item.key}"},
        "proposed_action": {
            "type": "nudge",
            "agent": "delegation",
            "title": f"Follow up with {person.name} on {item.key}",
            "payload": {
                "work_item_id": str(item.id),
                "person_id": str(person.id),
                "message": a.message,
            },
        },
        "citations": [cite("work_item", item.id, item.key)],
    }


# --------------------------------------------------------------------------- risk
class RiskyArgs(BaseModel):
    min_score: float = Field(default=0.6, ge=0, le=1)


async def get_risky_items(s: AsyncSession, ctx: TenantContext, a: RiskyArgs) -> dict[str, Any]:
    prog, _ = await _program_ids(s, ctx)
    items = await risk.risky_items(s, ctx, prog.id, a.min_score, MAX_ROWS)
    return {
        "data": [
            {
                "key": i.key,
                "title": i.title,
                "epic": i.epic,
                "owner": i.owner,
                "status": i.status,
                "probability": i.probability,
                "due": i.due_date,
                "drivers": [d.label for d in i.drivers],
            }
            for i in items
        ],
        "citations": [cite("work_item", i.work_item_id, i.key) for i in items[:6]],
    }


async def explain_prediction(s: AsyncSession, ctx: TenantContext, a: ItemRef) -> dict[str, Any]:
    item = await _item(s, ctx, a.work_item)
    p = (
        await s.execute(
            select(m.MlPrediction).where(
                m.MlPrediction.org_id == ctx.org_id, m.MlPrediction.entity_id == item.id
            )
        )
    ).scalar()
    if p is None:
        raise NotFoundError(f"No prediction for {item.key}")
    return {
        "data": {
            "key": item.key,
            "probability": p.score,
            "model_version": p.model_version,
            "drivers": p.drivers,
        },
        "citations": [cite("work_item", item.id, item.key)],
    }


async def get_dependency_graph(s: AsyncSession, ctx: TenantContext, a: NoArgs) -> dict[str, Any]:
    prog, _ = await _program_ids(s, ctx)
    g = await risk.dependency_graph(s, ctx, prog.id)
    by_id = {n.id: n for n in g.nodes}
    path = [by_id[i] for i in g.critical_path if i in by_id]
    epics = [n for n in g.nodes if n.kind == "epic"]
    return {
        "data": {
            "critical_path": [n.label for n in path],
            "epics": [
                {
                    "title": n.label,
                    "team": n.team,
                    "risk": n.risk,
                    "slack_days": n.slack_days,
                    "critical": n.critical,
                }
                for n in epics
            ],
        },
        "citations": [cite("epic", n.id, n.label) for n in path],
    }


class ImpactArgs(BaseModel):
    entity: str = Field(description="Epic title or work item key")
    slip_days: int = Field(ge=1, le=120)


async def impact_analysis(s: AsyncSession, ctx: TenantContext, a: ImpactArgs) -> dict[str, Any]:
    try:
        ent_id = (await _item(s, ctx, a.entity)).id
    except NotFoundError:
        ent_id = (await _epic(s, ctx, a.entity)).id
    out = await risk.impact(s, ctx, ent_id, a.slip_days)
    return {
        "data": out.model_dump(mode="json"),
        "citations": [cite(x["kind"], x["id"], x["label"]) for x in out.affected[:4]],
    }


async def run_forecast(s: AsyncSession, ctx: TenantContext, a: NoArgs) -> dict[str, Any]:
    _, ms = await _program_ids(s, ctx)
    latest, previous = await program.forecasts(s, ms.id)
    if latest is None:
        raise NotFoundError("No forecast yet")
    return {
        "data": {
            "milestone": ms.name,
            "target": ms.target_date,
            "p50": latest.p50_date,
            "p80": latest.p80_date,
            "p95": latest.p95_date,
            "p80_two_weeks_ago": previous.p80_date if previous else None,
            "days_late_at_p80": (latest.p80_date - ms.target_date).days,
            "on_time_probability": latest.distribution.get("on_time_probability"),
        },
        "citations": [
            cite("forecast", latest.id, f"Forecast {latest.run_at:%b %d}"),
            cite("milestone", ms.id, ms.name),
        ],
    }


class RiskUpdateArgs(BaseModel):
    title: str
    probability: float = Field(ge=0, le=1)
    impact: int = Field(ge=1, le=5)
    mitigation: str = ""


async def propose_risk_update(
    s: AsyncSession, ctx: TenantContext, a: RiskUpdateArgs
) -> dict[str, Any]:
    existing = (await s.execute(Repo(s, ctx, m.Risk).select(m.Risk.title == a.title))).scalar()
    payload: dict[str, Any] = a.model_dump()
    if existing is not None:
        payload["risk_id"] = str(existing.id)
    return {
        "data": {"proposed": f"Update risk: {a.title}"},
        "proposed_action": {
            "type": "risk_update",
            "agent": "risk",
            "title": f"Risk register: {a.title}",
            "payload": payload,
            "explanation": a.mitigation,
        },
        "citations": [cite("risk", existing.id, existing.title)] if existing else [],
    }


# --------------------------------------------------------------------------- comms
async def get_program_snapshot(s: AsyncSession, ctx: TenantContext, a: NoArgs) -> dict[str, Any]:
    prog, ms = await _program_ids(s, ctx)
    h = await program.health(s, ctx, prog.id)
    fc = await run_forecast(s, ctx, NoArgs())
    risky = await get_risky_items(s, ctx, RiskyArgs(min_score=0.7))
    since = date.today() - timedelta(days=14)
    done = (
        (
            await s.execute(
                Repo(s, ctx, m.WorkItem).select(
                    m.WorkItem.status == "done", m.WorkItem.done_at >= since
                )
            )
        )
        .scalars()
        .all()
    )
    epics = {e.id: e.title for e in await Repo(s, ctx, m.Epic).all()}
    wins: dict[str, int] = {}
    for w in done:
        title = epics.get(w.epic_id, "Other") if w.epic_id else "Other"
        wins[title] = wins.get(title, 0) + 1
    risks = await Repo(s, ctx, m.Risk).all(m.Risk.status != "closed")
    return {
        "data": {
            "program": prog.name,
            "target": ms.target_date,
            "health": h.score,
            "health_delta_7d": h.delta_7d,
            "subscores": h.subscores,
            "forecast": fc["data"],
            "completed_last_14d": len(done),
            "wins_by_epic": dict(sorted(wins.items(), key=lambda kv: -kv[1])[:4]),
            "top_risks": [
                {"title": r.title, "severity": r.severity, "status": r.status, "source": r.source}
                for r in sorted(risks, key=lambda r: -r.severity)[:4]
            ],
            "at_risk_items": risky["data"][:5],
        },
        "citations": [
            cite("program", prog.id, prog.name),
            *fc["citations"],
            *risky["citations"][:3],
            *[cite("risk", r.id, r.title) for r in risks[:2]],
        ],
    }


async def get_health(s: AsyncSession, ctx: TenantContext, a: NoArgs) -> dict[str, Any]:
    prog, _ = await _program_ids(s, ctx)
    h = await program.health(s, ctx, prog.id)
    return {
        "data": h.model_dump(mode="json", exclude={"trend"}),
        "citations": [cite("program", prog.id, prog.name)],
    }


async def search_decisions(s: AsyncSession, ctx: TenantContext, a: Query) -> dict[str, Any]:
    rows = await retrieval.search_decisions(s, ctx.org_id, a.query, limit=6)
    return {
        "data": [
            {
                "title": d.title,
                "chosen": d.chosen_option,
                "rationale": fence(d.rationale, "decision"),
                "decided": d.decided_at.date(),
            }
            for d, _ in rows
        ],
        "citations": [cite("decision", d.id, d.title) for d, _ in rows],
    }


class ExtractArgs(BaseModel):
    document: str | None = Field(default=None, description="Document title or id")
    text: str | None = Field(default=None, max_length=20000)


async def extract_actions(s: AsyncSession, ctx: TenantContext, a: ExtractArgs) -> dict[str, Any]:
    from twinpm.services import comms

    doc_id = None
    if a.document:
        repo = Repo(s, ctx, m.Document)
        try:
            doc_id = (await repo.get(uuid.UUID(a.document))).id
        except ValueError:
            row = (await s.execute(repo.select(m.Document.title.ilike(f"%{a.document}%")))).scalar()
            doc_id = row.id if row else None
    out = await comms.extract(s, ctx, doc_id, a.text, create_suggestions=False)
    return {
        "data": out.model_dump(mode="json"),
        "citations": [cite("document", doc_id, "source")] if doc_id else [],
    }


class ReportArgs(BaseModel):
    audience: Literal["executive", "engineering", "customer"] = "executive"
    title: str
    body: str = Field(min_length=20)


async def propose_status_report(
    s: AsyncSession, ctx: TenantContext, a: ReportArgs
) -> dict[str, Any]:
    return {
        "data": {"proposed": a.title},
        "proposed_action": {
            "type": "status_report",
            "agent": "comms",
            "title": a.title,
            "payload": a.model_dump(),
        },
    }


class DecisionArgs(BaseModel):
    title: str
    chosen_option: str
    rationale: str


async def log_decision(s: AsyncSession, ctx: TenantContext, a: DecisionArgs) -> dict[str, Any]:
    """Returns a decision record for the TPM to confirm; it is saved from the Comms Studio."""
    return {"data": {"decision": a.model_dump(), "status": "drafted for confirmation"}}


# --------------------------------------------------------------------------- insights
class MetricArgs(BaseModel):
    metric: Literal[
        "velocity", "throughput", "cycle_time_p50", "bug_inflow", "review_latency_p50", "wip"
    ]
    team: str | None = None
    days: int = Field(default=56, ge=7, le=365)


async def query_metric(s: AsyncSession, ctx: TenantContext, a: MetricArgs) -> dict[str, Any]:
    teams = await Repo(s, ctx, m.Team).all()
    ids = [t.id for t in teams if a.team and a.team.lower() in t.name.lower()]
    assert a.metric in METRICS
    series = await insights.query_metric(
        s, ctx, ids, a.metric, date.today() - timedelta(days=a.days), date.today()
    )
    data = []
    for sr in series:
        vals = [p.value for p in sr.points]
        half = len(vals) // 2
        data.append(
            {
                "team": sr.team,
                "latest": vals[-1] if vals else None,
                "first_half_mean": round(sum(vals[:half]) / max(half, 1), 2),
                "second_half_mean": round(sum(vals[half:]) / max(len(vals) - half, 1), 2),
                "anomalous_days": sum(p.anomaly for p in sr.points),
            }
        )
    return {
        "data": {"metric": a.metric, "days": a.days, "series": data},
        "citations": [cite("team", sr.team_id, sr.team) for sr in series],
    }


async def get_anomalies(s: AsyncSession, ctx: TenantContext, a: NoArgs) -> dict[str, Any]:
    rows = await Repo(s, ctx, m.Anomaly).all(m.Anomaly.status == "open")
    rows = sorted(rows, key=lambda r: -abs(r.z_score))[:MAX_ROWS]
    return {
        "data": [
            {"metric": r.metric, "date": r.date, "z": r.z_score, "explanation": r.explanation}
            for r in rows
        ],
        "citations": [cite("anomaly", r.id, r.metric) for r in rows[:4]],
    }


async def get_team_health(s: AsyncSession, ctx: TenantContext, a: NoArgs) -> dict[str, Any]:
    prog, _ = await _program_ids(s, ctx)
    rows = await insights.team_health(s, ctx, prog.id)
    return {
        "data": [r.model_dump(mode="json", exclude={"series"}) for r in rows],
        "citations": [cite("team", r.team_id, r.team) for r in rows],
    }


SPECS: dict[str, tuple[str, type[BaseModel], ToolFn]] = {
    "search_feedback": ("Semantic search over customer feedback.", Query, search_feedback),
    "get_themes": ("Feedback themes with opportunity scores and quotes.", NoArgs, get_themes),
    "score_opportunity": (
        "Opportunity score breakdown for one theme.",
        ThemeRef,
        score_opportunity,
    ),
    "get_objectives": ("Program OKRs.", NoArgs, get_objectives),
    "rag_search": (
        "Hybrid search over design docs, meeting notes and transcripts.",
        RagArgs,
        rag_search,
    ),
    "draft_document": (
        "Section outline plus retrieved context for a draft.",
        DraftArgs,
        draft_document,
    ),
    "get_epic": ("Epic details and open items.", EpicRef, get_epic),
    "estimate_effort": (
        "ML effort estimates with similar past items.",
        EstimateArgs,
        estimate_effort,
    ),
    "get_capacity": (
        "Next-sprint capacity and recommended commitment for a team.",
        TeamRef,
        get_capacity,
    ),
    "compare_options": (
        "Simulate rebalance, descope and date-shift responses to the current slip.",
        NoArgs,
        compare_options,
    ),
    "simulate_scenario": (
        "Simulate one option or a team capacity change.",
        SimArgs,
        simulate_scenario,
    ),
    "get_roadmap": ("Now/next/later roadmap with RICE and risk.", NoArgs, get_roadmap),
    "get_workload": ("Per-person utilisation, skills and growth goals.", NoArgs, get_workload),
    "rank_candidates": (
        "Ranked owners for a work item with factor breakdown.",
        ItemRef,
        rank_candidates,
    ),
    "propose_reassignment": (
        "Propose moving work items to a person (needs policy approval).",
        ReassignArgs,
        propose_reassignment,
    ),
    "propose_rebalance": (
        "Plan and propose moves off the critical path.",
        NoArgs,
        propose_rebalance,
    ),
    "find_stalled_items": (
        "Items stuck in a status or waiting on review.",
        NoArgs,
        find_stalled_items,
    ),
    "propose_nudge": ("Propose a follow-up message to an item's owner.", NudgeArgs, propose_nudge),
    "get_risky_items": (
        "Open items with delay probability and SHAP drivers.",
        RiskyArgs,
        get_risky_items,
    ),
    "explain_prediction": (
        "SHAP drivers for one item's delay prediction.",
        ItemRef,
        explain_prediction,
    ),
    "get_dependency_graph": ("Critical path and epic slack.", NoArgs, get_dependency_graph),
    "impact_analysis": (
        "Cascade and forecast impact of an N-day slip.",
        ImpactArgs,
        impact_analysis,
    ),
    "run_forecast": (
        "Latest launch forecast (P50/P80/P95) and the one from two weeks ago.",
        NoArgs,
        run_forecast,
    ),
    "propose_risk_update": (
        "Propose a risk register change (needs policy approval).",
        RiskUpdateArgs,
        propose_risk_update,
    ),
    "get_program_snapshot": (
        "Health, forecast, wins, risks and at-risk items.",
        NoArgs,
        get_program_snapshot,
    ),
    "get_health": ("Program health score, sub-scores and drivers.", NoArgs, get_health),
    "search_decisions": ("Search the decision log.", Query, search_decisions),
    "extract_actions": (
        "Extract decisions and action items from a document or transcript.",
        ExtractArgs,
        extract_actions,
    ),
    "propose_status_report": (
        "Propose sending a status report (needs approval).",
        ReportArgs,
        propose_status_report,
    ),
    "log_decision": ("Draft a decision record for confirmation.", DecisionArgs, log_decision),
    "query_metric": (
        "Parameterised team metric series (no free-form queries).",
        MetricArgs,
        query_metric,
    ),
    "get_anomalies": ("Open metric anomalies with explanations.", NoArgs, get_anomalies),
    "get_team_health": (
        "Team-level sentiment and load (teams under 5 suppressed).",
        NoArgs,
        get_team_health,
    ),
}

AGENT_TOOLS: dict[str, list[str]] = {
    "strategy": [
        "search_feedback",
        "get_themes",
        "score_opportunity",
        "get_objectives",
        "rag_search",
        "draft_document",
    ],
    "planner": [
        "get_epic",
        "estimate_effort",
        "get_capacity",
        "compare_options",
        "simulate_scenario",
        "get_roadmap",
    ],
    "delegation": [
        "get_workload",
        "rank_candidates",
        "propose_reassignment",
        "propose_rebalance",
        "find_stalled_items",
        "propose_nudge",
    ],
    "risk": [
        "get_risky_items",
        "explain_prediction",
        "get_dependency_graph",
        "impact_analysis",
        "run_forecast",
        "propose_risk_update",
    ],
    "comms": [
        "get_program_snapshot",
        "get_health",
        "rag_search",
        "search_decisions",
        "extract_actions",
        "propose_status_report",
        "log_decision",
    ],
    "insights": ["query_metric", "get_anomalies", "get_team_health"],
}
WRITE_TOOLS = {
    "propose_reassignment",
    "propose_rebalance",
    "propose_nudge",
    "propose_risk_update",
    "propose_status_report",
}
_TOOLS: dict[str, BaseTool] = {}


def get_tool(name: str) -> BaseTool:
    if name not in _TOOLS:
        desc, schema, fn = SPECS[name]
        _TOOLS[name] = make_tool(name, desc, schema, fn)
    return _TOOLS[name]


def tools_for(agent: str) -> list[BaseTool]:
    return [get_tool(n) for n in AGENT_TOOLS[agent]]

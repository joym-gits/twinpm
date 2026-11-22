"""Background graphs run by the worker: morning briefing, nudges and risk-register upkeep.

They reuse the same services and the same autonomy policy gate as chat.
"""

from __future__ import annotations

import uuid
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy import select

from twinpm.core.tenancy import TenantContext
from twinpm.db import models as m
from twinpm.db.session import get_sessionmaker
from twinpm.services import delegation, ml_jobs, program, suggestions


class BgState(TypedDict, total=False):
    org_id: str
    user_id: str
    program_id: str
    result: dict[str, Any]


async def _ctx(state: BgState) -> TenantContext:
    async with get_sessionmaker()() as s:
        user = await s.get(m.User, uuid.UUID(state["user_id"]))
        assert user is not None
    return TenantContext(
        org_id=uuid.UUID(state["org_id"]), user_id=user.id, role=user.role, actor_type="twin"
    )


async def briefing_node(state: BgState) -> dict[str, Any]:
    ctx = await _ctx(state)
    async with get_sessionmaker()() as s:
        b = await program.briefing(s, ctx, uuid.UUID(state["program_id"]), refresh=True)
        if b.items:
            await suggestions.create(
                s,
                ctx,
                type="alert",
                agent="briefing",
                title=f"Morning briefing: {b.items[0].title}"[:300],
                payload={
                    "title": "Your morning briefing is ready",
                    "body": " | ".join(i.title for i in b.items),
                    "link": "/command-center",
                },
                explanation=b.items[0].why,
                program_id=uuid.UUID(state["program_id"]),
            )
        await s.commit()
    return {"result": {"items": len(b.items)}}


async def nudge_node(state: BgState) -> dict[str, Any]:
    ctx = await _ctx(state)
    async with get_sessionmaker()() as s:
        out = await delegation.run_nudges(s, ctx, uuid.UUID(state["program_id"]))
        await s.commit()
    return {"result": out.model_dump()}


async def risk_review_node(state: BgState) -> dict[str, Any]:
    async with get_sessionmaker()() as s:
        out = await ml_jobs.refresh_org(s, uuid.UUID(state["org_id"]))
    return {"result": out}


def _single(name: str, fn: Any) -> Any:
    g: StateGraph[BgState] = StateGraph(BgState)
    g.add_node(name, fn)
    g.add_edge(START, name)
    g.add_edge(name, END)
    return g.compile(name=f"{name}_graph")


briefing_graph = _single("briefing", briefing_node)
nudge_graph = _single("nudge", nudge_node)
risk_review_graph = _single("risk_review", risk_review_node)


async def owner_state(org_id: uuid.UUID) -> BgState | None:
    """State for an org's main program and its TPM owner."""
    async with get_sessionmaker()() as s:
        prog = (
            await s.execute(
                select(m.Program)
                .where(m.Program.org_id == org_id, m.Program.deleted_at.is_(None))
                .order_by(m.Program.created_at)
                .limit(1)
            )
        ).scalar_one_or_none()
        has_milestone = prog is not None and await s.scalar(
            select(m.Milestone.id).where(m.Milestone.program_id == prog.id).limit(1)
        )
    if prog is None or prog.owner_user_id is None or not has_milestone:
        return None
    return {"org_id": str(org_id), "user_id": str(prog.owner_user_id), "program_id": str(prog.id)}

"""Process-wide agent runtime: LangGraph Postgres checkpointer, compiled graphs, resumes."""

from __future__ import annotations

import asyncio
import uuid
from contextlib import AsyncExitStack
from typing import Any

from langgraph.types import Command
from sqlalchemy import select

from twinpm.config import get_settings
from twinpm.core.logging import get_logger
from twinpm.core.tenancy import TenantContext
from twinpm.db import models as m
from twinpm.db.session import get_sessionmaker
from twinpm.services import suggestions

log = get_logger(__name__)
_stack: AsyncExitStack | None = None
_graph: Any = None
_tasks: set[asyncio.Task[Any]] = set()


def checkpoint_dsn() -> str:
    """psycopg DSN for the app database, with LangGraph tables in the `langgraph` schema."""
    url = get_settings().database_url.replace("postgresql+asyncpg://", "postgresql://")
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}options=-csearch_path%3Dlanggraph"


async def open_checkpointer(stack: AsyncExitStack) -> Any:
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    saver = await stack.enter_async_context(AsyncPostgresSaver.from_conn_string(checkpoint_dsn()))
    await saver.setup()
    return saver


async def startup_agent_runtime() -> None:
    global _stack, _graph
    from twinpm.agents.graphs.supervisor import build_supervisor

    _stack = AsyncExitStack()
    try:
        _graph = build_supervisor(await open_checkpointer(_stack))
    except Exception as exc:  # keep serving non-agent routes if Postgres is briefly unavailable
        log.error("agent_runtime_unavailable", error=str(exc))
        _graph = None


async def shutdown_agent_runtime() -> None:
    global _stack, _graph
    for t in list(_tasks):
        t.cancel()
    if _stack is not None:
        await _stack.aclose()
    _stack, _graph = None, None


async def get_graph() -> Any:
    if _graph is None:
        await startup_agent_runtime()
    if _graph is None:
        raise RuntimeError("Agent runtime is not available")
    return _graph


async def resume_config(thread_id: str) -> Any:
    """Rebuild the run config for a paused thread `{org_id}:{conversation_id}`."""
    from twinpm.agents.graphs.supervisor import run_config

    org_s, conv_s = thread_id.split(":", 1)
    async with get_sessionmaker()() as s:
        conv = await s.get(m.Conversation, uuid.UUID(conv_s))
        if conv is None or str(conv.org_id) != org_s:
            raise LookupError(f"Unknown thread {thread_id}")
        user = await s.get(m.User, conv.user_id)
        persona = (
            await s.execute(
                select(m.PersonaProfile).where(m.PersonaProfile.user_id == conv.user_id)
            )
        ).scalar_one_or_none()
    assert user is not None
    ctx = TenantContext(org_id=conv.org_id, user_id=user.id, role=user.role)
    return run_config(
        ctx,
        thread_id=thread_id,
        conversation_id=str(conv.id),
        program_id=str(conv.program_id) if conv.program_id else None,
        user_name=user.name,
        persona=persona,
    )


async def resume_thread(thread_id: str, value: dict[str, Any]) -> dict[str, Any]:
    graph = await get_graph()
    config = await resume_config(thread_id)
    result: dict[str, Any] = await graph.ainvoke(Command(resume=value), config)
    return result


async def _resume_when_settled(s_id: uuid.UUID, thread_id: str, value: dict[str, Any]) -> None:
    """Wait for the response to commit; resume once no suggestion in the thread is pending."""
    for _ in range(50):
        async with get_sessionmaker()() as s:
            rows = (
                await s.execute(
                    select(m.Suggestion.id, m.Suggestion.status).where(
                        m.Suggestion.thread_id == thread_id
                    )
                )
            ).all()
        mine = next((st for i, st in rows if i == s_id), "pending")
        if mine != "pending":
            if any(st == "pending" for _, st in rows):
                return  # wait for the remaining approvals
            try:
                await resume_thread(thread_id, value)
            except Exception as exc:
                log.error("resume_failed", thread_id=thread_id, error=str(exc))
            return
        await asyncio.sleep(0.1)


async def _on_response(s: m.Suggestion, value: dict[str, Any]) -> None:
    if not s.thread_id or _graph is None:
        return
    task = asyncio.create_task(
        _resume_when_settled(s.id, s.thread_id, {**value, "suggestion_id": str(s.id)})
    )
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


suggestions.on_response(_on_response)

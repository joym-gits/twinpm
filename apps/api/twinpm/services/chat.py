"""Ask the Twin: conversations and streamed agent runs mapped to SSE events."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any

from langchain_core.messages import HumanMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from twinpm.agents.demo_rules import AGENTS
from twinpm.agents.graphs.supervisor import run_config
from twinpm.agents.guardrails import Redactor
from twinpm.agents.runtime import get_graph
from twinpm.core.logging import get_logger
from twinpm.core.tenancy import TenantContext
from twinpm.db import models as m
from twinpm.db.repository import Repo

log = get_logger(__name__)


def thread_id(org_id: uuid.UUID, conversation_id: uuid.UUID) -> str:
    return f"{org_id}:{conversation_id}"


async def create_conversation(
    session: AsyncSession, ctx: TenantContext, program_id: uuid.UUID | None, title: str | None
) -> m.Conversation:
    c = Repo(session, ctx, m.Conversation).add(
        m.Conversation(
            user_id=ctx.user_id, program_id=program_id, title=title or "New conversation"
        )
    )
    await session.flush()
    return c


async def get_conversation(
    session: AsyncSession, ctx: TenantContext, cid: uuid.UUID
) -> tuple[m.Conversation, list[m.Message]]:
    c = await Repo(session, ctx, m.Conversation).get(cid)
    msgs = (
        (
            await session.execute(
                select(m.Message)
                .where(m.Message.conversation_id == cid)
                .order_by(m.Message.created_at)
            )
        )
        .scalars()
        .all()
    )
    return c, list(msgs)


def _summarise_tool_output(output: Any) -> str:
    import json

    raw = getattr(output, "content", output)
    try:
        data = json.loads(raw if isinstance(raw, str) else "{}").get("data")
    except (json.JSONDecodeError, AttributeError):
        return "ok"
    if isinstance(data, list):
        return f"{len(data)} result(s)"
    if isinstance(data, dict):
        if data.get("error"):
            return f"error: {data['error']}"
        keys = [k for k in ("p80", "health", "narrative", "proposed") if k in data]
        return "; ".join(f"{k}: {str(data[k])[:80]}" for k in keys) or "ok"
    return "ok"


async def stream_message(
    session: AsyncSession,
    ctx: TenantContext,
    cid: uuid.UUID,
    content: str,
    page_context: dict[str, Any] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    conv = await Repo(session, ctx, m.Conversation).get(cid)
    user = await session.get(m.User, ctx.user_id)
    persona = (
        await session.execute(
            select(m.PersonaProfile).where(
                m.PersonaProfile.org_id == ctx.org_id, m.PersonaProfile.user_id == ctx.user_id
            )
        )
    ).scalar_one_or_none()
    session.add(m.Message(org_id=ctx.org_id, conversation_id=conv.id, role="user", content=content))
    if conv.title == "New conversation":
        conv.title = content[:80]
    await session.commit()
    tid = thread_id(ctx.org_id, conv.id)
    config = run_config(
        ctx,
        thread_id=tid,
        conversation_id=str(conv.id),
        program_id=str(conv.program_id) if conv.program_id else None,
        user_name=user.name if user else "TPM",
        persona=persona,
    )
    graph = await get_graph()
    # PII is redacted before it reaches any model; the stored user message keeps the original.
    question = Redactor().redact(content)
    inputs = {
        "messages": [HumanMessage(content=question)],
        "question": question,
        "page_context": page_context or {},
    }
    trace: list[dict[str, Any]] = []
    try:
        async for ev in graph.astream_events(inputs, config, version="v2"):
            kind, name = ev["event"], ev.get("name", "")
            node = (ev.get("metadata") or {}).get("langgraph_node")
            if kind == "on_chain_start" and name in AGENTS:
                trace.append({"agent": name, "event": "agent_started"})
                yield {"event": "agent_started", "data": {"agent": name}}
            elif kind == "on_tool_start":
                yield {
                    "event": "tool_call",
                    "data": {"tool": name, "args": ev["data"].get("input", {})},
                }
            elif kind == "on_tool_end":
                yield {
                    "event": "tool_result",
                    "data": {
                        "tool": name,
                        "summary": _summarise_tool_output(ev["data"].get("output")),
                    },
                }
            elif kind == "on_chat_model_stream" and node == "compose_answer":
                chunk = ev["data"]["chunk"]
                text = (
                    chunk.content
                    if isinstance(chunk.content, str)
                    else "".join(c.get("text", "") for c in chunk.content if isinstance(c, dict))
                )
                if text:
                    yield {"event": "token", "data": {"text": text}}
    except Exception as exc:
        log.exception("chat_run_failed", error=str(exc))
        yield {
            "event": "error",
            "data": {"message": "The twin hit an error and stopped.", "trace": trace},
        }
        return
    state = await graph.aget_state(config)
    values = state.values
    for sid in values.get("suggestion_ids", []):
        yield {"event": "suggestion_created", "data": {"id": sid}}
    last = values["messages"][-1]
    for c in last.additional_kwargs.get("citations", []):
        yield {"event": "citation", "data": c}
    if state.next and values.get("pending_approval"):
        yield {"event": "approval_required", "data": values["pending_approval"]}
        yield {
            "event": "done",
            "data": {
                "status": "awaiting_approval",
                "text": values.get("answer", ""),
                "warnings": values.get("warnings", []),
                "agent_trace": values.get("agent_trace", []),
            },
        }
        return
    last = values["messages"][-1]
    for c in last.additional_kwargs.get("citations", []):
        yield {"event": "citation", "data": c}
    yield {
        "event": "done",
        "data": {
            "status": "complete",
            "text": values.get("answer", ""),
            "warnings": values.get("warnings", []),
            "agent_trace": values.get("agent_trace", []),
        },
    }

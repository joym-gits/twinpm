"""Suggestions: how the twin proposes actions, and how the TPM's responses teach it."""

from __future__ import annotations

import difflib
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from twinpm.core.errors import ConflictError, ForbiddenError
from twinpm.core.rbac import Perm, has_perm
from twinpm.core.tenancy import TenantContext
from twinpm.db import models as m
from twinpm.db.repository import Repo
from twinpm.ml import preference
from twinpm.services import actions, audit, events, policy

EXPIRY = timedelta(days=7)
MAX_STYLE_EXAMPLES = 10
# Called after a response so a paused agent graph can resume (registered by the agent runtime).
ResumeHook = Callable[[m.Suggestion, dict[str, Any]], Awaitable[None]]
_resume_hooks: list[ResumeHook] = []


def on_response(hook: ResumeHook) -> None:
    _resume_hooks.append(hook)


def _features(s: m.Suggestion) -> dict[str, float]:
    drivers = s.drivers or []
    top = max((abs(float(d.get("contribution", 0))) for d in drivers), default=0.0)
    f = preference.context_features(
        s.type,
        s.autonomy_level_required,
        len(drivers),
        len(s.citations or []),
        top,
        float(s.payload.get("risk", 0) or 0),
    )
    for k, v in (s.payload.get("factors") or {}).items():
        f[f"factor_{k}"] = float(v)
    return f


async def create(
    session: AsyncSession,
    ctx: TenantContext,
    *,
    type: str,
    title: str,
    payload: dict[str, Any],
    agent: str,
    explanation: str = "",
    drivers: list[dict[str, Any]] | None = None,
    citations: list[dict[str, Any]] | None = None,
    program_id: uuid.UUID | None = None,
    thread_id: str | None = None,
) -> m.Suggestion | None:
    """Route a twin proposal through the autonomy policy.

    L1: notification only (returns None). L2/L3: pending suggestion. L4: executed now, with
    status `auto_executed` and undo available.
    """
    actions.validate(type, payload)
    decision = await policy.decide_for(session, ctx.org_id, ctx.user_id, type, program_id)
    if decision.notify_only:
        session.add(
            m.Notification(
                org_id=ctx.org_id,
                user_id=ctx.user_id,
                kind="twin_observe",
                title=f"Twin noticed: {title}",
                body=explanation,
            )
        )
        await audit.record(
            session,
            ctx.as_twin(),
            action="twin.observed",
            entity_type="suggestion",
            entity_id=None,
            after={"type": type, "title": title},
        )
        return None
    s = Repo(session, ctx, m.Suggestion).add(
        m.Suggestion(
            program_id=program_id,
            user_id=ctx.user_id,
            agent=agent,
            type=type,
            title=title,
            payload=payload,
            explanation=explanation,
            drivers=drivers or [],
            citations=citations or [],
            autonomy_level_required=int(decision.level),
            status="pending",
            thread_id=thread_id,
            expires_at=datetime.now(UTC) + EXPIRY,
            result={},
        )
    )
    await session.flush()
    await audit.record(
        session,
        ctx.as_twin(),
        action="suggestion.created",
        entity_type="suggestion",
        entity_id=s.id,
        suggestion_id=s.id,
        after={"type": type, "title": title, "level": int(decision.level)},
    )
    if decision.execute_now:
        s.result = await actions.execute(
            session, ctx.as_twin(), type, payload, suggestion_id=s.id, program_id=program_id
        )
        s.status = "auto_executed"
        s.responded_at = datetime.now(UTC)
        session.add(
            m.Notification(
                org_id=ctx.org_id,
                user_id=ctx.user_id,
                kind="twin_action",
                title=f"Twin did: {title}",
                body=explanation,
                link=f"/suggestions/{s.id}",
            )
        )
    await events.publish(
        ctx.org_id, "suggestion.created", {"id": str(s.id), "type": type, "status": s.status}
    )
    return s


def _diff(before: str, after: str) -> str:
    return "\n".join(
        difflib.unified_diff(before.splitlines(), after.splitlines(), lineterm="", n=0)
    )


async def _learn_style(session: AsyncSession, ctx: TenantContext, before: str, after: str) -> None:
    """Keep edited lines from status reports as style examples (most recent 10)."""
    added = [
        ln.removeprefix("+").strip()
        for ln in _diff(before, after).splitlines()
        if ln.startswith("+") and not ln.startswith("+++") and len(ln.strip()) > 12
    ]
    if not added:
        return
    persona = (
        await session.execute(
            select(m.PersonaProfile).where(
                m.PersonaProfile.org_id == ctx.org_id, m.PersonaProfile.user_id == ctx.user_id
            )
        )
    ).scalar_one_or_none()
    if persona is None:
        persona = m.PersonaProfile(
            org_id=ctx.org_id,
            user_id=ctx.user_id,
            priorities=[],
            style_examples=[],
            escalation_rules=[],
            working_hours={},
            delegation_weights={},
        )
        session.add(persona)
    persona.style_examples = [*added, *(persona.style_examples or [])][:MAX_STYLE_EXAMPLES]


async def respond(
    session: AsyncSession,
    ctx: TenantContext,
    sid: uuid.UUID,
    action: str,
    edited_payload: dict[str, Any] | None = None,
    reason: str | None = None,
) -> m.Suggestion:
    s = await actions.get_suggestion(session, ctx, sid)
    if s.status != "pending":
        raise ConflictError(f"Suggestion is already {s.status}")
    if s.expires_at and s.expires_at < datetime.now(UTC):
        s.status = "expired"
        raise ConflictError("Suggestion has expired")
    perm = actions.PERMISSIONS[s.type]
    allowed = (
        has_perm(ctx.role, perm)
        if action != "reject"
        else (has_perm(ctx.role, perm) or has_perm(ctx.role, Perm.SUGGESTION_RESPOND))
    )
    if not allowed:
        raise ForbiddenError(f"Role '{ctx.role}' cannot {action} '{s.type}' suggestions")
    edit_diff = None
    payload = s.payload
    if action == "edit":
        if not edited_payload:
            raise ConflictError("edit needs edited_payload")
        payload = {**s.payload, **edited_payload}
        if s.type == "status_report":
            edit_diff = _diff(str(s.payload.get("body", "")), str(payload.get("body", "")))
            await _learn_style(
                session, ctx, str(s.payload.get("body", "")), str(payload.get("body", ""))
            )
        s.payload = payload
    if action in ("accept", "edit"):
        s.result = await actions.execute(
            session,
            ctx,
            s.type,
            payload,
            suggestion_id=s.id,
            approved=True,
            program_id=s.program_id,
        )
        s.status = "edited" if action == "edit" else "accepted"
    else:
        s.status = "rejected"
    s.responded_by = ctx.user_id
    s.responded_at = datetime.now(UTC)
    s.feedback_reason = reason
    session.add(
        m.PreferenceEvent(
            org_id=ctx.org_id,
            user_id=ctx.user_id,
            suggestion_id=s.id,
            suggestion_type=s.type,
            context_features=_features(s),
            outcome=s.status,
            edit_diff=edit_diff,
        )
    )
    await audit.record(
        session,
        ctx,
        action=f"suggestion.{s.status}",
        entity_type="suggestion",
        entity_id=s.id,
        suggestion_id=s.id,
        reason=reason,
        after={"status": s.status},
    )
    await session.flush()
    await events.publish(ctx.org_id, "suggestion.responded", {"id": str(s.id), "status": s.status})
    for hook in _resume_hooks:
        await hook(s, {"action": action, "payload": payload, "reason": reason})
    return s


async def undo(session: AsyncSession, ctx: TenantContext, sid: uuid.UUID) -> m.Suggestion:
    s = await actions.get_suggestion(session, ctx, sid)
    await actions.undo(session, ctx, s)
    return s

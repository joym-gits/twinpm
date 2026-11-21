"""Suggestions, persona, autonomy policy, twin learning, audit and notifications."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Query
from sqlalchemy import select

from twinpm.core.errors import NotFoundError
from twinpm.db.models import Notification, Suggestion
from twinpm.db.repository import Repo
from twinpm.deps import DB, AuditCtx, Ctx, PersonaCtx, ReadCtx, RespondCtx
from twinpm.schemas.program import AuditEntry
from twinpm.schemas.twin import (
    AutonomyOut,
    AutonomyUpdate,
    LearningStats,
    NotificationOut,
    PersonaOut,
    PersonaUpdate,
    RespondRequest,
    SuggestionOut,
)
from twinpm.services import audit, suggestions, twin

router = APIRouter(tags=["twin"])


@router.get("/suggestions", response_model=list[SuggestionOut])
async def list_suggestions(
    ctx: ReadCtx,
    session: DB,
    status: str | None = "pending",
    type: str | None = None,
    program_id: uuid.UUID | None = None,
    limit: int = Query(50, ge=1, le=200),
) -> list[SuggestionOut]:
    where = []
    if status:
        where.append(Suggestion.status == status)
    if type:
        where.append(Suggestion.type == type)
    if program_id:
        where.append(Suggestion.program_id == program_id)
    page = await Repo(session, ctx, Suggestion).page(*where, limit=limit)
    return [SuggestionOut.model_validate(s) for s in page.items]


@router.get("/suggestions/{suggestion_id}", response_model=SuggestionOut)
async def get_suggestion(suggestion_id: uuid.UUID, ctx: ReadCtx, session: DB) -> SuggestionOut:
    return SuggestionOut.model_validate(await Repo(session, ctx, Suggestion).get(suggestion_id))


@router.post("/suggestions/{suggestion_id}/respond", response_model=SuggestionOut)
async def respond(
    suggestion_id: uuid.UUID, body: RespondRequest, ctx: Ctx, session: DB
) -> SuggestionOut:
    """Accept, edit or reject. Accepting runs the Action Executor and teaches the twin."""
    s = await suggestions.respond(
        session, ctx, suggestion_id, body.action, body.edited_payload, body.reason
    )
    return SuggestionOut.model_validate(s)


@router.post("/suggestions/{suggestion_id}/undo", response_model=SuggestionOut)
async def undo(suggestion_id: uuid.UUID, ctx: RespondCtx, session: DB) -> SuggestionOut:
    """Reverse an executed, reversible action within 24 hours."""
    return SuggestionOut.model_validate(await suggestions.undo(session, ctx, suggestion_id))


@router.get("/persona", response_model=PersonaOut)
async def get_persona(ctx: ReadCtx, session: DB) -> PersonaOut:
    return await twin.get_persona(session, ctx)


@router.put("/persona", response_model=PersonaOut)
async def put_persona(body: PersonaUpdate, ctx: PersonaCtx, session: DB) -> PersonaOut:
    return await twin.put_persona(session, ctx, body)


@router.get("/autonomy-policy", response_model=AutonomyOut)
async def get_autonomy(
    ctx: ReadCtx, session: DB, program_id: uuid.UUID | None = None
) -> AutonomyOut:
    return await twin.get_autonomy(session, ctx, program_id)


@router.put("/autonomy-policy", response_model=AutonomyOut)
async def put_autonomy(body: AutonomyUpdate, ctx: PersonaCtx, session: DB) -> AutonomyOut:
    return await twin.put_autonomy(session, ctx, body.program_id, body.levels)


@router.get("/twin/learning", response_model=LearningStats)
async def learning(ctx: ReadCtx, session: DB) -> LearningStats:
    return await twin.learning_stats(session, ctx)


@router.get("/audit", response_model=list[AuditEntry])
async def get_audit(
    ctx: AuditCtx,
    session: DB,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    actor_type: str | None = None,
    suggestion_id: uuid.UUID | None = None,
    before_id: int | None = None,
    limit: int = Query(50, ge=1, le=200),
) -> list[AuditEntry]:
    rows = await audit.query(
        session,
        ctx,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_type=actor_type,
        suggestion_id=suggestion_id,
        before_id=before_id,
        limit=limit,
    )
    return [AuditEntry.model_validate(r) for r in rows]


@router.get("/notifications", response_model=list[NotificationOut])
async def notifications(
    ctx: ReadCtx, session: DB, unread: bool = False, limit: int = Query(30, ge=1, le=100)
) -> list[NotificationOut]:
    where = [Notification.user_id == ctx.user_id]
    if unread:
        where.append(Notification.read_at.is_(None))
    page = await Repo(session, ctx, Notification).page(*where, limit=limit)
    return [NotificationOut.model_validate(n) for n in page.items]


@router.post("/notifications/{notification_id}/read", response_model=NotificationOut)
async def mark_read(notification_id: uuid.UUID, ctx: ReadCtx, session: DB) -> NotificationOut:
    n = (
        await session.execute(
            select(Notification).where(
                Notification.id == notification_id,
                Notification.org_id == ctx.org_id,
                Notification.user_id == ctx.user_id,
            )
        )
    ).scalar_one_or_none()
    if n is None:
        raise NotFoundError("Notification not found")
    n.read_at = n.read_at or datetime.now(UTC)
    return NotificationOut.model_validate(n)

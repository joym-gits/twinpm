"""Append-only audit log writer. There is deliberately no update or delete API."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from twinpm.core.tenancy import TenantContext
from twinpm.db.models import AuditLog


async def record(
    session: AsyncSession,
    ctx: TenantContext,
    *,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID | None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    reason: str | None = None,
    suggestion_id: uuid.UUID | None = None,
    actor_type: str | None = None,
) -> AuditLog:
    entry = AuditLog(
        org_id=ctx.org_id,
        actor_type=actor_type or ctx.actor_type,
        actor_id=ctx.user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        before=before,
        after=after,
        reason=reason,
        suggestion_id=suggestion_id,
        request_id=ctx.request_id,
        ip=ctx.ip,
    )
    session.add(entry)
    await session.flush()
    return entry


async def query(
    session: AsyncSession,
    ctx: TenantContext,
    *,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    actor_type: str | None = None,
    suggestion_id: uuid.UUID | None = None,
    before_id: int | None = None,
    limit: int = 50,
) -> Sequence[AuditLog]:
    stmt = select(AuditLog).where(AuditLog.org_id == ctx.org_id)
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if entity_id:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    if actor_type:
        stmt = stmt.where(AuditLog.actor_type == actor_type)
    if suggestion_id:
        stmt = stmt.where(AuditLog.suggestion_id == suggestion_id)
    if before_id:
        stmt = stmt.where(AuditLog.id < before_id)
    stmt = stmt.order_by(AuditLog.id.desc()).limit(limit)
    return (await session.execute(stmt)).scalars().all()

"""Run a connector sync for one integration and record the outcome."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from twinpm.config import get_settings
from twinpm.connectors.base import SyncResult
from twinpm.connectors.mock import tracker
from twinpm.core.tenancy import TenantContext
from twinpm.db import models as m
from twinpm.services import audit, events


async def sync_integration(
    session: AsyncSession, ctx: TenantContext, integ: m.Integration
) -> SyncResult:
    if integ.mode == "live":
        from twinpm.connectors.live import sync_live

        res = await sync_live(session, ctx, integ)
    elif integ.provider in ("jira", "github") and get_settings().demo_live_ticks:
        res = await tracker.tick(session, ctx.org_id, integ.provider)
    else:
        res = SyncResult(integ.provider, details=["mock: no changes"])
    integ.last_sync_at = datetime.now(UTC)
    integ.status = "connected"
    await audit.record(
        session,
        ctx,
        action="integration.synced",
        entity_type="integration",
        entity_id=integ.id,
        actor_type="system",
        after={
            "provider": integ.provider,
            "mode": integ.mode,
            "updated": res.updated,
            "events": res.events,
        },
    )
    await session.flush()
    if res.events:
        await events.publish(
            ctx.org_id, "connector.synced", {"provider": integ.provider, "events": res.events}
        )
    return res

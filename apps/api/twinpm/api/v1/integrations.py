"""Integrations: provider cards, mock/live mode and manual sync."""

from __future__ import annotations

import uuid

from fastapi import APIRouter

from twinpm.connectors.sync import sync_integration
from twinpm.core.crypto import encrypt_config
from twinpm.db.models import Integration
from twinpm.db.repository import Repo
from twinpm.deps import DB, IntegrationsCtx, ReadCtx
from twinpm.schemas.twin import IntegrationOut, IntegrationPatch, SyncOut
from twinpm.services import audit

router = APIRouter(prefix="/integrations", tags=["integrations"])


def _out(i: Integration) -> IntegrationOut:
    o = IntegrationOut.model_validate(i)
    o.configured = bool(i.config)
    return o


@router.get("", response_model=list[IntegrationOut])
async def list_integrations(ctx: ReadCtx, session: DB) -> list[IntegrationOut]:
    return [
        _out(i) for i in await Repo(session, ctx, Integration).all(order_by=Integration.provider)
    ]


@router.patch("/{integration_id}", response_model=IntegrationOut)
async def patch(
    integration_id: uuid.UUID, body: IntegrationPatch, ctx: IntegrationsCtx, session: DB
) -> IntegrationOut:
    """Switch mock/live and store config. Secrets are Fernet-encrypted at rest."""
    i = await Repo(session, ctx, Integration).get(integration_id)
    before = {"mode": i.mode, "configured": bool(i.config)}
    if body.config is not None:
        i.config = encrypt_config(body.config)
    if body.mode:
        i.mode = body.mode
    await audit.record(
        session,
        ctx,
        action="integration.updated",
        entity_type="integration",
        entity_id=i.id,
        before=before,
        after={"mode": i.mode, "configured": bool(i.config)},
    )
    return _out(i)


@router.post("/{integration_id}/sync", response_model=SyncOut)
async def sync(integration_id: uuid.UUID, ctx: IntegrationsCtx, session: DB) -> SyncOut:
    i = await Repo(session, ctx, Integration).get(integration_id)
    res = await sync_integration(session, ctx, i)
    return SyncOut(
        provider=res.provider,
        created=res.created,
        updated=res.updated,
        events=res.events,
        details=res.details,
    )

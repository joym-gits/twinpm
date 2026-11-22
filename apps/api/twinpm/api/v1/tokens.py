"""Per-user API tokens (for MCP clients and automation)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Response
from pydantic import BaseModel, Field

from twinpm.core.security import new_opaque_token, token_digest
from twinpm.db.models import ApiToken
from twinpm.db.repository import Repo
from twinpm.deps import API_TOKEN_PREFIX, DB, Ctx
from twinpm.schemas.common import ORM
from twinpm.services import audit

router = APIRouter(prefix="/api-tokens", tags=["platform"])


class TokenCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class TokenOut(ORM):
    id: uuid.UUID
    name: str
    prefix: str
    last_used_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime


class TokenCreated(TokenOut):
    token: str


@router.post("", response_model=TokenCreated, status_code=201)
async def create(body: TokenCreate, ctx: Ctx, session: DB) -> TokenCreated:
    """The token is shown once. Only its SHA-256 digest is stored."""
    raw = new_opaque_token(API_TOKEN_PREFIX)
    row = Repo(session, ctx, ApiToken).add(
        ApiToken(user_id=ctx.user_id, name=body.name, token_hash=token_digest(raw), prefix=raw[:10])
    )
    await session.flush()
    await audit.record(
        session,
        ctx,
        action="api_token.created",
        entity_type="api_token",
        entity_id=row.id,
        after={"name": body.name},
    )
    return TokenCreated(**TokenOut.model_validate(row).model_dump(), token=raw)


@router.get("", response_model=list[TokenOut])
async def list_tokens(ctx: Ctx, session: DB) -> list[TokenOut]:
    rows = await Repo(session, ctx, ApiToken).all(ApiToken.user_id == ctx.user_id)
    return [TokenOut.model_validate(r) for r in rows]


@router.delete("/{token_id}", status_code=204)
async def revoke(token_id: uuid.UUID, ctx: Ctx, session: DB) -> Response:
    row = await Repo(session, ctx, ApiToken).get(token_id)
    if row.user_id == ctx.user_id and row.revoked_at is None:
        row.revoked_at = datetime.now(UTC)
        await audit.record(
            session, ctx, action="api_token.revoked", entity_type="api_token", entity_id=row.id
        )
    return Response(status_code=204)

"""FastAPI dependencies: DB session, authenticated tenant context, RBAC."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Coroutine
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from twinpm.core.errors import ForbiddenError, UnauthorizedError
from twinpm.core.logging import request_id_var
from twinpm.core.rbac import Perm, ensure
from twinpm.core.security import (
    ACCESS_COOKIE,
    CSRF_COOKIE,
    CSRF_HEADER,
    decode_access_token,
    token_digest,
)
from twinpm.core.tenancy import TenantContext
from twinpm.db.models import ApiToken, Person, User
from twinpm.db.session import get_sessionmaker

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
API_TOKEN_PREFIX = "tpm_"  # noqa: S105 - a public prefix, not a secret


async def get_db() -> AsyncIterator[AsyncSession]:
    async with get_sessionmaker()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


DB = Annotated[AsyncSession, Depends(get_db)]


async def _ctx_for_user(session: AsyncSession, user: User, request: Request) -> TenantContext:
    person_id = (
        await session.execute(
            select(Person.id).where(Person.user_id == user.id, Person.org_id == user.org_id)
        )
    ).scalar_one_or_none()
    return TenantContext(
        org_id=user.org_id,
        user_id=user.id,
        role=user.role,
        request_id=request_id_var.get(),
        ip=request.client.host if request.client else None,
        person_id=person_id,
    )


async def resolve_api_token(session: AsyncSession, raw: str) -> User:
    tok = (
        await session.execute(
            select(ApiToken).where(
                ApiToken.token_hash == token_digest(raw), ApiToken.revoked_at.is_(None)
            )
        )
    ).scalar_one_or_none()
    if tok is None:
        raise UnauthorizedError("Invalid API token")
    tok.last_used_at = datetime.now(UTC)
    user = await session.get(User, tok.user_id)
    if user is None or not user.is_active:
        raise UnauthorizedError("Invalid API token")
    return user


async def get_ctx(request: Request, session: DB) -> TenantContext:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        raw = auth[7:].strip()
        if raw.startswith(API_TOKEN_PREFIX):
            return await _ctx_for_user(session, await resolve_api_token(session, raw), request)
        claims = decode_access_token(raw)
    else:
        cookie = request.cookies.get(ACCESS_COOKIE)
        if not cookie:
            raise UnauthorizedError("Not authenticated")
        claims = decode_access_token(cookie)
        # CSRF: double-submit cookie for cookie-authenticated mutations.
        if request.method not in SAFE_METHODS:
            sent = request.headers.get(CSRF_HEADER)
            if not sent or sent != request.cookies.get(CSRF_COOKIE):
                raise ForbiddenError("CSRF token missing or invalid")
    user = await session.get(User, claims.user_id)
    if user is None or not user.is_active or user.org_id != claims.org_id:
        raise UnauthorizedError("User not found or inactive")
    return await _ctx_for_user(session, user, request)


Ctx = Annotated[TenantContext, Depends(get_ctx)]


def require(perm: Perm) -> Callable[..., Coroutine[Any, Any, TenantContext]]:
    async def _dep(ctx: Ctx) -> TenantContext:
        ensure(ctx, perm)
        return ctx

    return _dep


ReadCtx = Annotated[TenantContext, Depends(require(Perm.READ))]
ProgramWriteCtx = Annotated[TenantContext, Depends(require(Perm.PROGRAM_WRITE))]
RiskWriteCtx = Annotated[TenantContext, Depends(require(Perm.RISK_WRITE))]
AiCtx = Annotated[TenantContext, Depends(require(Perm.AI_USE))]
RespondCtx = Annotated[TenantContext, Depends(require(Perm.SUGGESTION_RESPOND))]
PersonaCtx = Annotated[TenantContext, Depends(require(Perm.PERSONA_WRITE))]
AdminCtx = Annotated[TenantContext, Depends(require(Perm.MEMBERS_MANAGE))]
OrgSettingsCtx = Annotated[TenantContext, Depends(require(Perm.ORG_SETTINGS))]
IntegrationsCtx = Annotated[TenantContext, Depends(require(Perm.INTEGRATIONS_MANAGE))]
AuditCtx = Annotated[TenantContext, Depends(require(Perm.AUDIT_READ))]

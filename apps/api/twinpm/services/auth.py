"""Authentication: login, refresh-token rotation with reuse detection, logout."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from twinpm.config import get_settings
from twinpm.core.errors import UnauthorizedError
from twinpm.core.logging import get_logger
from twinpm.core.security import (
    create_access_token,
    hash_password,
    new_opaque_token,
    token_digest,
    verify_password,
)
from twinpm.db.models import Organization, RefreshToken, User

log = get_logger(__name__)
# Constant-time-ish failure path: verify against a real hash even when the user is unknown.
_DUMMY_HASH = hash_password("dummy-password-for-timing")


@dataclass(frozen=True)
class IssuedTokens:
    access_token: str
    refresh_token: str
    user: User


async def _issue(session: AsyncSession, user: User, family_id: uuid.UUID) -> IssuedTokens:
    refresh = new_opaque_token()
    session.add(
        RefreshToken(
            org_id=user.org_id,
            user_id=user.id,
            family_id=family_id,
            token_hash=token_digest(refresh),
            expires_at=datetime.now(UTC)
            + timedelta(seconds=get_settings().jwt_refresh_ttl_seconds),
        )
    )
    access = create_access_token(user.id, user.org_id, user.role)
    await session.flush()
    return IssuedTokens(access, refresh, user)


async def login(
    session: AsyncSession, email: str, password: str, org_slug: str | None = None
) -> IssuedTokens:
    stmt = select(User).where(
        User.email == email.lower().strip(), User.is_active.is_(True), User.deleted_at.is_(None)
    )
    if org_slug:
        stmt = stmt.join(Organization, Organization.id == User.org_id).where(
            Organization.slug == org_slug
        )
    users = list((await session.execute(stmt)).scalars())
    if len(users) != 1:
        verify_password(_DUMMY_HASH, password)
        raise UnauthorizedError("Invalid email or password")
    user = users[0]
    if not verify_password(user.password_hash, password):
        raise UnauthorizedError("Invalid email or password")
    user.last_login_at = datetime.now(UTC)
    return await _issue(session, user, uuid.uuid4())


async def refresh(session: AsyncSession, refresh_token: str) -> IssuedTokens:
    row = (
        await session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_digest(refresh_token))
        )
    ).scalar_one_or_none()
    now = datetime.now(UTC)
    if row is None or row.revoked_at is not None or row.expires_at < now:
        raise UnauthorizedError("Invalid refresh token")
    if row.used_at is not None:
        # Reuse of a rotated token: assume theft, revoke the whole family.
        await revoke_family(session, row.family_id)
        # Commit now: the request fails with 401, which would otherwise roll this back.
        await session.commit()
        log.warning("refresh_token_reuse_detected", user_id=str(row.user_id))
        raise UnauthorizedError("Refresh token reuse detected; session revoked")
    row.used_at = now
    user = await session.get(User, row.user_id)
    if user is None or not user.is_active or user.deleted_at is not None:
        raise UnauthorizedError("User is inactive")
    return await _issue(session, user, row.family_id)


async def revoke_family(session: AsyncSession, family_id: uuid.UUID) -> None:
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )


async def logout(session: AsyncSession, refresh_token: str | None) -> None:
    if not refresh_token:
        return
    row = (
        await session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_digest(refresh_token))
        )
    ).scalar_one_or_none()
    if row is not None:
        await revoke_family(session, row.family_id)

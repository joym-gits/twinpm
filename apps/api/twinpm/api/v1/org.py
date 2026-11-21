"""Organisation and member management."""

from __future__ import annotations

import uuid

from fastapi import APIRouter
from sqlalchemy import func, select

from twinpm.core.errors import ConflictError, NotFoundError
from twinpm.core.security import hash_password
from twinpm.db.models import Organization, User
from twinpm.db.repository import Repo
from twinpm.deps import DB, AdminCtx, OrgSettingsCtx, ReadCtx
from twinpm.schemas.auth import MemberCreate, MemberUpdate, OrgOut, OrgSettingsUpdate, UserOut
from twinpm.services import audit

router = APIRouter(tags=["org"])


@router.get("/org", response_model=OrgOut)
async def get_org(ctx: ReadCtx, session: DB) -> OrgOut:
    org = await session.get(Organization, ctx.org_id)
    if org is None:
        raise NotFoundError("Organisation not found")
    return OrgOut.model_validate(org)


@router.patch("/org/settings", response_model=OrgOut)
async def update_org_settings(body: OrgSettingsUpdate, ctx: OrgSettingsCtx, session: DB) -> OrgOut:
    org = await session.get(Organization, ctx.org_id)
    if org is None:
        raise NotFoundError("Organisation not found")
    before = dict(org.settings)
    org.settings = {**org.settings, **body.settings}
    await audit.record(
        session,
        ctx,
        action="org.settings_updated",
        entity_type="organization",
        entity_id=org.id,
        before=before,
        after=org.settings,
    )
    return OrgOut.model_validate(org)


@router.get("/members", response_model=list[UserOut])
async def list_members(ctx: AdminCtx, session: DB) -> list[UserOut]:
    rows = await Repo(session, ctx, User).all(order_by=User.name)
    return [UserOut.model_validate(u) for u in rows]


@router.post("/members", response_model=UserOut, status_code=201)
async def create_member(body: MemberCreate, ctx: AdminCtx, session: DB) -> UserOut:
    repo = Repo(session, ctx, User)
    exists = await session.scalar(
        select(func.count())
        .select_from(User)
        .where(User.org_id == ctx.org_id, User.email == body.email.lower())
    )
    if exists:
        raise ConflictError("A member with this email already exists")
    user = repo.add(
        User(
            email=body.email.lower(),
            name=body.name,
            role=body.role,
            password_hash=hash_password(body.password),
            is_active=True,
        )
    )
    await session.flush()
    await audit.record(
        session,
        ctx,
        action="member.created",
        entity_type="user",
        entity_id=user.id,
        after={"email": user.email, "role": user.role},
    )
    return UserOut.model_validate(user)


@router.patch("/members/{user_id}", response_model=UserOut)
async def update_member(
    user_id: uuid.UUID, body: MemberUpdate, ctx: AdminCtx, session: DB
) -> UserOut:
    user = await Repo(session, ctx, User).get(user_id)
    before = {"name": user.name, "role": user.role, "is_active": user.is_active}
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(user, field, value)
    await audit.record(
        session,
        ctx,
        action="member.updated",
        entity_type="user",
        entity_id=user.id,
        before=before,
        after={"name": user.name, "role": user.role, "is_active": user.is_active},
    )
    return UserOut.model_validate(user)

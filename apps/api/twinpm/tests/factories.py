"""Small builders for test data."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from twinpm.core.security import hash_password
from twinpm.core.tenancy import TenantContext
from twinpm.db.models import Organization, Program, User

PASSWORD = "correct-horse-battery-staple"


@dataclass
class OrgFixture:
    org: Organization
    users: dict[str, User]
    program: Program

    def ctx(self, role: str = "tpm") -> TenantContext:
        u = self.users[role]
        return TenantContext(org_id=self.org.id, user_id=u.id, role=u.role)


async def make_org(session: AsyncSession, slug: str | None = None) -> OrgFixture:
    slug = slug or f"org-{uuid.uuid4().hex[:8]}"
    org = Organization(name=slug.title(), slug=slug, plan="enterprise", settings={})
    session.add(org)
    await session.flush()
    users: dict[str, User] = {}
    pw = hash_password(PASSWORD)
    for role in ("org_admin", "tpm", "eng_manager", "executive", "member", "viewer"):
        u = User(
            org_id=org.id,
            email=f"{role}@{slug}.test",
            name=f"{role.title()} User",
            password_hash=pw,
            role=role,
            is_active=True,
        )
        session.add(u)
        users[role] = u
    await session.flush()
    program = Program(org_id=org.id, name="Program", objective="", owner_user_id=users["tpm"].id)
    session.add(program)
    await session.commit()
    return OrgFixture(org, users, program)

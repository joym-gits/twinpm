"""Authenticated request context. Every repository query is scoped by `ctx.org_id`."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field


@dataclass(frozen=True)
class TenantContext:
    org_id: uuid.UUID
    user_id: uuid.UUID | None
    role: str
    actor_type: str = "user"  # user | twin | system
    request_id: str | None = None
    ip: str | None = None
    person_id: uuid.UUID | None = None
    scopes: frozenset[str] = field(default_factory=frozenset)

    def as_twin(self) -> TenantContext:
        """Same tenant and owner, acting as the twin (subject to the autonomy policy)."""
        return TenantContext(
            org_id=self.org_id,
            user_id=self.user_id,
            role=self.role,
            actor_type="twin",
            request_id=self.request_id,
            ip=self.ip,
            person_id=self.person_id,
            scopes=self.scopes,
        )

    @classmethod
    def system(cls, org_id: uuid.UUID, owner_user_id: uuid.UUID | None = None) -> TenantContext:
        return cls(org_id=org_id, user_id=owner_user_id, role="org_admin", actor_type="system")

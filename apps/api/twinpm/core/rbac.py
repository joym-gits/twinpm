"""Role-based access control. Roles map to permissions; routes declare what they need."""

from __future__ import annotations

from enum import StrEnum

from twinpm.core.errors import ForbiddenError
from twinpm.core.tenancy import TenantContext


class Perm(StrEnum):
    READ = "read"
    PROGRAM_WRITE = "program:write"
    RISK_WRITE = "risk:write"
    SUGGESTION_RESPOND = "suggestion:respond"
    COMMS_APPROVE = "comms:approve"
    AI_USE = "ai:use"
    PERSONA_WRITE = "persona:write"
    MEMBERS_MANAGE = "members:manage"
    ORG_SETTINGS = "org:settings"
    INTEGRATIONS_MANAGE = "integrations:manage"
    AUDIT_READ = "audit:read"
    ADMIN = "admin"


_ALL = frozenset(Perm)
ROLE_PERMISSIONS: dict[str, frozenset[Perm]] = {
    "org_admin": _ALL,
    "tpm": frozenset(
        {
            Perm.READ,
            Perm.PROGRAM_WRITE,
            Perm.RISK_WRITE,
            Perm.SUGGESTION_RESPOND,
            Perm.COMMS_APPROVE,
            Perm.AI_USE,
            Perm.PERSONA_WRITE,
            Perm.AUDIT_READ,
            Perm.INTEGRATIONS_MANAGE,
        }
    ),
    "eng_manager": frozenset(
        {
            Perm.READ,
            Perm.PROGRAM_WRITE,
            Perm.RISK_WRITE,
            Perm.SUGGESTION_RESPOND,
            Perm.AI_USE,
            Perm.PERSONA_WRITE,
            Perm.AUDIT_READ,
        }
    ),
    # Executives: read-only plus comms approval.
    "executive": frozenset({Perm.READ, Perm.COMMS_APPROVE, Perm.AI_USE, Perm.AUDIT_READ}),
    "member": frozenset({Perm.READ, Perm.AI_USE, Perm.PERSONA_WRITE}),
    "viewer": frozenset({Perm.READ}),
}


def has_perm(role: str, perm: Perm) -> bool:
    return perm in ROLE_PERMISSIONS.get(role, frozenset())


def ensure(ctx: TenantContext, perm: Perm) -> None:
    if not has_perm(ctx.role, perm):
        raise ForbiddenError(f"Role '{ctx.role}' lacks permission '{perm.value}'")

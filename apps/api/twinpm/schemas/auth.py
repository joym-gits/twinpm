"""Auth and organisation schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from twinpm.schemas.common import ORM

# Syntactic check only: reserved demo domains such as `.example` must be accepted.
Email = Annotated[str, Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=320)]

Role = Literal["org_admin", "tpm", "eng_manager", "executive", "member", "viewer"]


class LoginRequest(BaseModel):
    email: Email
    password: str = Field(min_length=1, max_length=256)
    org_slug: str | None = None

    model_config = {
        "json_schema_extra": {
            "examples": [{"email": "priya@novapay.example", "password": "TwinPM-demo-2026!"}]
        }
    }


class OrgOut(ORM):
    id: uuid.UUID
    name: str
    slug: str
    plan: str
    settings: dict[str, Any]


class UserOut(ORM):
    id: uuid.UUID
    email: str
    name: str
    role: Role
    is_active: bool
    last_login_at: datetime | None
    timezone: str


class MeResponse(BaseModel):
    user: UserOut
    org: OrgOut
    person_id: uuid.UUID | None
    permissions: list[str]
    demo_mode: bool
    default_program_id: uuid.UUID | None


class SessionResponse(BaseModel):
    user: UserOut
    org_slug: str
    csrf_token: str


class DemoUser(BaseModel):
    email: str
    name: str
    role: Role


class MemberCreate(BaseModel):
    email: Email
    name: str = Field(min_length=1, max_length=200)
    role: Role
    password: str = Field(min_length=12, max_length=256)


class MemberUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    role: Role | None = None
    is_active: bool | None = None


class OrgSettingsUpdate(BaseModel):
    settings: dict[str, Any]

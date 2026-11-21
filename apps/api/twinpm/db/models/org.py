"""Tenancy, identity and workforce tables."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from twinpm.db.base import Base, IdTimestampMixin, SoftDeleteMixin, TenantMixin

ROLES = ("org_admin", "tpm", "eng_manager", "executive", "member", "viewer")


class Organization(IdTimestampMixin, Base):
    __tablename__ = "organizations"
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    plan: Mapped[str] = mapped_column(String(40), default="enterprise")
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class User(TenantMixin, SoftDeleteMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("org_id", "email", name="uq_users_org_email"),
        CheckConstraint(f"role IN {ROLES}", name="role"),
    )
    email: Mapped[str] = mapped_column(String(320))
    name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(32))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")


class RefreshToken(TenantMixin, Base):
    """Refresh-token family for rotation with reuse detection."""

    __tablename__ = "refresh_tokens"
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    family_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ApiToken(TenantMixin, Base):
    """Per-user API tokens (used by the MCP server)."""

    __tablename__ = "api_tokens"
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    prefix: Mapped[str] = mapped_column(String(12))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Team(TenantMixin, SoftDeleteMixin, Base):
    __tablename__ = "teams"
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    manager_person_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("people.id", use_alter=True, ondelete="SET NULL")
    )


class Person(TenantMixin, SoftDeleteMixin, Base):
    __tablename__ = "people"
    name: Mapped[str] = mapped_column(String(200))
    title: Mapped[str] = mapped_column(String(200))
    team_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("teams.id", ondelete="SET NULL"), index=True
    )
    capacity_hours_per_week: Mapped[float] = mapped_column(Float, default=40.0)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    growth_goals: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    avatar_url: Mapped[str | None] = mapped_column(String(500))
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )


class Skill(TenantMixin, Base):
    __tablename__ = "skills"
    __table_args__ = (UniqueConstraint("org_id", "name", name="uq_skills_org_name"),)
    name: Mapped[str] = mapped_column(String(80))
    category: Mapped[str] = mapped_column(String(80))


class PersonSkill(TenantMixin, Base):
    __tablename__ = "person_skills"
    __table_args__ = (
        UniqueConstraint("person_id", "skill_id", name="uq_person_skills_person_skill"),
        CheckConstraint("level BETWEEN 1 AND 5", name="level"),
    )
    person_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("people.id", ondelete="CASCADE"), index=True
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("skills.id", ondelete="CASCADE"), index=True
    )
    level: Mapped[int] = mapped_column(Integer)
    evidence_count: Mapped[int] = mapped_column(Integer, default=0)


class TimeOff(TenantMixin, Base):
    """PTO, used by sprint planning capacity and the delegation PTO-overlap penalty."""

    __tablename__ = "time_off"
    person_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("people.id", ondelete="CASCADE"), index=True
    )
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    kind: Mapped[str] = mapped_column(String(32), default="pto")

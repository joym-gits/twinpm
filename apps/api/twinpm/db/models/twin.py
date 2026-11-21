"""Twin tables: suggestions, scenarios, persona, autonomy, preferences, audit, chat, platform."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from twinpm.db.base import Base, TenantMixin

SUGGESTION_TYPES = (
    "reassign",
    "create_task",
    "status_report",
    "risk_update",
    "nudge",
    "roadmap_change",
    "scenario",
    "alert",
)
SUGGESTION_STATUSES = ("pending", "accepted", "edited", "rejected", "auto_executed", "expired")


def _fk(table: str, nullable: bool = True, ondelete: str = "SET NULL") -> Any:
    return mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{table}.id", ondelete=ondelete),
        index=True,
        nullable=nullable,
    )


class Suggestion(TenantMixin, Base):
    __tablename__ = "suggestions"
    __table_args__ = (
        CheckConstraint(f"type IN {SUGGESTION_TYPES}", name="type"),
        CheckConstraint(f"status IN {SUGGESTION_STATUSES}", name="status"),
        CheckConstraint("autonomy_level_required BETWEEN 1 AND 4", name="level"),
        Index("ix_suggestions_org_status", "org_id", "status"),
    )
    program_id: Mapped[uuid.UUID | None] = _fk("programs", ondelete="CASCADE")
    user_id: Mapped[uuid.UUID | None] = _fk("users")  # twin owner the suggestion is for
    agent: Mapped[str] = mapped_column(String(32))
    type: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(300))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    explanation: Mapped[str] = mapped_column(Text, default="")
    drivers: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    citations: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    autonomy_level_required: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    responded_by: Mapped[uuid.UUID | None] = _fk("users")
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    feedback_reason: Mapped[str | None] = mapped_column(Text)
    result: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)  # executor output + undo
    thread_id: Mapped[str | None] = mapped_column(String(64))  # LangGraph thread awaiting it
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    undone_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Scenario(TenantMixin, Base):
    __tablename__ = "scenarios"
    program_id: Mapped[uuid.UUID] = _fk("programs", nullable=False, ondelete="CASCADE")
    name: Mapped[str] = mapped_column(String(200))
    changes: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    result: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_by: Mapped[uuid.UUID | None] = _fk("users")


class PersonaProfile(TenantMixin, Base):
    __tablename__ = "persona_profiles"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_persona_profiles_user_id"),
        CheckConstraint("tone IN ('concise', 'detailed', 'formal', 'friendly')", name="tone"),
        CheckConstraint("risk_tolerance IN ('low', 'medium', 'high')", name="risk_tolerance"),
    )
    user_id: Mapped[uuid.UUID] = _fk("users", nullable=False, ondelete="CASCADE")
    priorities: Mapped[list[str]] = mapped_column(JSONB, default=list)
    style_examples: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    tone: Mapped[str] = mapped_column(String(16), default="concise")
    risk_tolerance: Mapped[str] = mapped_column(String(8), default="medium")
    escalation_rules: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    working_hours: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    delegation_weights: Mapped[dict[str, float]] = mapped_column(JSONB, default=dict)


class AutonomyPolicy(TenantMixin, Base):
    __tablename__ = "autonomy_policies"
    __table_args__ = (
        CheckConstraint("level BETWEEN 1 AND 4", name="level"),
        UniqueConstraint(
            "user_id",
            "program_id",
            "action_type",
            name="uq_autonomy_user_program_action",
            postgresql_nulls_not_distinct=True,
        ),
    )
    user_id: Mapped[uuid.UUID] = _fk("users", nullable=False, ondelete="CASCADE")
    program_id: Mapped[uuid.UUID | None] = _fk("programs", ondelete="CASCADE")
    action_type: Mapped[str] = mapped_column(String(32))
    level: Mapped[int] = mapped_column(Integer)


class PreferenceEvent(TenantMixin, Base):
    __tablename__ = "preference_events"
    user_id: Mapped[uuid.UUID] = _fk("users", nullable=False, ondelete="CASCADE")
    suggestion_id: Mapped[uuid.UUID | None] = _fk("suggestions")
    suggestion_type: Mapped[str] = mapped_column(String(32))
    context_features: Mapped[dict[str, Any]] = mapped_column(JSONB)
    outcome: Mapped[str] = mapped_column(String(16))
    edit_diff: Mapped[str | None] = mapped_column(Text)


class AuditLog(Base):
    """Append-only. UPDATE and DELETE are rejected by a database trigger."""

    __tablename__ = "audit_log"
    __table_args__ = (
        CheckConstraint("actor_type IN ('user', 'twin', 'system')", name="actor_type"),
        Index("ix_audit_log_entity", "org_id", "entity_type", "entity_id"),
        Index("ix_audit_log_org_time", "org_id", "occurred_at"),
    )
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    actor_type: Mapped[str] = mapped_column(String(8))
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    action: Mapped[str] = mapped_column(String(64))
    entity_type: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    reason: Mapped[str | None] = mapped_column(Text)
    suggestion_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    request_id: Mapped[str | None] = mapped_column(String(64))
    ip: Mapped[str | None] = mapped_column(INET)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Notification(TenantMixin, Base):
    __tablename__ = "notifications"
    user_id: Mapped[uuid.UUID] = _fk("users", nullable=False, ondelete="CASCADE")
    kind: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text, default="")
    link: Mapped[str | None] = mapped_column(String(500))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Conversation(TenantMixin, Base):
    __tablename__ = "conversations"
    user_id: Mapped[uuid.UUID] = _fk("users", nullable=False, ondelete="CASCADE")
    program_id: Mapped[uuid.UUID | None] = _fk("programs", ondelete="CASCADE")
    title: Mapped[str] = mapped_column(String(300), default="New conversation")
    summary: Mapped[str] = mapped_column(Text, default="")


class Message(TenantMixin, Base):
    __tablename__ = "messages"
    conversation_id: Mapped[uuid.UUID] = _fk("conversations", nullable=False, ondelete="CASCADE")
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    tool_calls: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    citations: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    agent_trace: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)


class Integration(TenantMixin, Base):
    __tablename__ = "integrations"
    __table_args__ = (
        UniqueConstraint("org_id", "provider", name="uq_integrations_org_provider"),
        CheckConstraint("mode IN ('mock', 'live')", name="mode"),
    )
    provider: Mapped[str] = mapped_column(String(32))
    mode: Mapped[str] = mapped_column(String(8), default="mock")
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)  # secrets Fernet-encrypted
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32), default="connected")


class LlmCall(TenantMixin, Base):
    __tablename__ = "llm_calls"
    user_id: Mapped[uuid.UUID | None] = _fk("users")
    purpose: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(64))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[float] = mapped_column(Float, default=0)
    cost_estimate_usd: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(String(16))
    prompt_version: Mapped[str | None] = mapped_column(String(32))
    request_id: Mapped[str | None] = mapped_column(String(64))

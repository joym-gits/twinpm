"""Program delivery tables: programs, OKRs, initiatives, epics, work items, dependencies."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from twinpm.db.base import Base, SoftDeleteMixin, TenantMixin

WORK_ITEM_STATUSES = ("todo", "in_progress", "in_review", "blocked", "done")
WORK_ITEM_TYPES = ("story", "task", "bug", "spike")
BUCKETS = ("now", "next", "later")
DEP_TYPES = ("initiative", "epic", "work_item")


def _fk(table: str, *, nullable: bool = True, ondelete: str = "SET NULL") -> Any:
    return mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{table}.id", ondelete=ondelete),
        index=True,
        nullable=nullable,
    )


class Program(TenantMixin, SoftDeleteMixin, Base):
    __tablename__ = "programs"
    name: Mapped[str] = mapped_column(String(200))
    objective: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="active")
    target_date: Mapped[date | None] = mapped_column(Date)
    owner_user_id: Mapped[uuid.UUID | None] = _fk("users")
    health_weights: Mapped[dict[str, float]] = mapped_column(JSONB, default=dict)


class Objective(TenantMixin, Base):
    __tablename__ = "objectives"
    program_id: Mapped[uuid.UUID] = _fk("programs", nullable=False, ondelete="CASCADE")
    title: Mapped[str] = mapped_column(String(300))
    key_results: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    quarter: Mapped[str] = mapped_column(String(16))


class Initiative(TenantMixin, SoftDeleteMixin, Base):
    __tablename__ = "initiatives"
    __table_args__ = (CheckConstraint(f"roadmap_bucket IN {BUCKETS}", name="bucket"),)
    program_id: Mapped[uuid.UUID] = _fk("programs", nullable=False, ondelete="CASCADE")
    objective_id: Mapped[uuid.UUID | None] = _fk("objectives")
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    roadmap_bucket: Mapped[str] = mapped_column(String(8), default="next")
    rice: Mapped[dict[str, float]] = mapped_column(JSONB, default=dict)
    wsjf: Mapped[dict[str, float]] = mapped_column(JSONB, default=dict)
    target_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(32), default="planned")


class Epic(TenantMixin, SoftDeleteMixin, Base):
    __tablename__ = "epics"
    initiative_id: Mapped[uuid.UUID | None] = _fk("initiatives")
    team_id: Mapped[uuid.UUID | None] = _fk("teams")
    key: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="in_progress")
    target_date: Mapped[date | None] = mapped_column(Date)


class WorkItem(TenantMixin, SoftDeleteMixin, Base):
    __tablename__ = "work_items"
    __table_args__ = (
        UniqueConstraint("org_id", "key", name="uq_work_items_org_key"),
        CheckConstraint(f"status IN {WORK_ITEM_STATUSES}", name="status"),
        CheckConstraint(f"type IN {WORK_ITEM_TYPES}", name="type"),
        Index("ix_work_items_status_due", "status", "due_date"),
    )
    epic_id: Mapped[uuid.UUID | None] = _fk("epics")
    team_id: Mapped[uuid.UUID | None] = _fk("teams")
    key: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    type: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16))
    story_points: Mapped[float] = mapped_column(Float, default=0)
    estimate_days: Mapped[float | None] = mapped_column(Float)
    assignee_person_id: Mapped[uuid.UUID | None] = _fk("people")
    created_at_src: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    due_date: Mapped[date | None] = mapped_column(Date)
    reopen_count: Mapped[int] = mapped_column(Integer, default=0)
    pr_review_hours: Mapped[float] = mapped_column(Float, default=0)
    comments_count: Mapped[int] = mapped_column(Integer, default=0)
    labels: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    external_ref: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class WorkItemEvent(TenantMixin, Base):
    __tablename__ = "work_item_events"
    work_item_id: Mapped[uuid.UUID] = _fk("work_items", nullable=False, ondelete="CASCADE")
    event_type: Mapped[str] = mapped_column(String(32))
    from_value: Mapped[str | None] = mapped_column(String(200))
    to_value: Mapped[str | None] = mapped_column(String(200))
    actor_person_id: Mapped[uuid.UUID | None] = _fk("people")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class Dependency(TenantMixin, Base):
    __tablename__ = "dependencies"
    __table_args__ = (
        CheckConstraint(f"from_type IN {DEP_TYPES}", name="from_type"),
        CheckConstraint(f"to_type IN {DEP_TYPES}", name="to_type"),
        Index("ix_dependencies_from", "from_type", "from_id"),
        Index("ix_dependencies_to", "to_type", "to_id"),
    )
    # Semantics: `from` blocks `to` (to depends on from) when kind == "blocks".
    from_type: Mapped[str] = mapped_column(String(16))
    from_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    to_type: Mapped[str] = mapped_column(String(16))
    to_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    kind: Mapped[str] = mapped_column(String(16), default="blocks")
    owning_team_id: Mapped[uuid.UUID | None] = _fk("teams")
    status: Mapped[str] = mapped_column(String(16), default="open")


class Sprint(TenantMixin, Base):
    __tablename__ = "sprints"
    team_id: Mapped[uuid.UUID] = _fk("teams", nullable=False, ondelete="CASCADE")
    name: Mapped[str] = mapped_column(String(80))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    goal: Mapped[str] = mapped_column(Text, default="")
    committed_points: Mapped[float] = mapped_column(Float, default=0)
    completed_points: Mapped[float] = mapped_column(Float, default=0)


class Milestone(TenantMixin, Base):
    __tablename__ = "milestones"
    program_id: Mapped[uuid.UUID] = _fk("programs", nullable=False, ondelete="CASCADE")
    name: Mapped[str] = mapped_column(String(200))
    target_date: Mapped[date] = mapped_column(Date)
    scope: Mapped[list[str]] = mapped_column(JSONB, default=list)  # epic IDs
    latest_forecast: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

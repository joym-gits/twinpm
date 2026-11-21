"""Team signals, daily metrics, ML outputs, forecasts, anomalies and health snapshots."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import Date, DateTime, Float, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from twinpm.db.base import Base, TenantMixin


def _fk(table: str, nullable: bool = False) -> Any:
    return mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{table}.id", ondelete="CASCADE"),
        index=True,
        nullable=nullable,
    )


class TeamSignal(TenantMixin, Base):
    """Team-level aggregates only. Never per person."""

    __tablename__ = "team_signals"
    __table_args__ = (UniqueConstraint("team_id", "date", name="uq_team_signals_team_date"),)
    team_id: Mapped[uuid.UUID] = _fk("teams")
    date: Mapped[date] = mapped_column(Date)
    sentiment_index: Mapped[float] = mapped_column(Float)
    message_volume: Mapped[float] = mapped_column(Float)
    after_hours_ratio: Mapped[float] = mapped_column(Float)


class MetricDaily(TenantMixin, Base):
    __tablename__ = "metrics_daily"
    __table_args__ = (UniqueConstraint("team_id", "date", name="uq_metrics_daily_team_date"),)
    team_id: Mapped[uuid.UUID] = _fk("teams")
    date: Mapped[date] = mapped_column(Date)
    velocity: Mapped[float] = mapped_column(Float)
    throughput: Mapped[float] = mapped_column(Float)
    cycle_time_p50: Mapped[float] = mapped_column(Float)
    bug_inflow: Mapped[float] = mapped_column(Float)
    review_latency_p50: Mapped[float] = mapped_column(Float)
    wip: Mapped[float] = mapped_column(Float)


class MlPrediction(TenantMixin, Base):
    __tablename__ = "ml_predictions"
    __table_args__ = (Index("ix_ml_predictions_entity", "entity_type", "entity_id", "model_name"),)
    entity_type: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    model_name: Mapped[str] = mapped_column(String(64))
    model_version: Mapped[str] = mapped_column(String(16))
    score: Mapped[float] = mapped_column(Float)
    drivers: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    predicted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Forecast(TenantMixin, Base):
    __tablename__ = "forecasts"
    milestone_id: Mapped[uuid.UUID] = _fk("milestones")
    p50_date: Mapped[date] = mapped_column(Date)
    p80_date: Mapped[date] = mapped_column(Date)
    p95_date: Mapped[date] = mapped_column(Date)
    distribution: Mapped[dict[str, Any]] = mapped_column(JSONB)
    assumptions: Mapped[dict[str, Any]] = mapped_column(JSONB)
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class Anomaly(TenantMixin, Base):
    __tablename__ = "anomalies"
    team_id: Mapped[uuid.UUID] = _fk("teams")
    metric: Mapped[str] = mapped_column(String(64))
    date: Mapped[date] = mapped_column(Date)
    value: Mapped[float] = mapped_column(Float)
    expected: Mapped[float] = mapped_column(Float)
    z_score: Mapped[float] = mapped_column(Float)
    method: Mapped[str] = mapped_column(String(32))
    explanation: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="open")


class HealthSnapshot(TenantMixin, Base):
    """Daily program health snapshot, powering the trend line."""

    __tablename__ = "health_snapshots"
    __table_args__ = (UniqueConstraint("program_id", "date", name="uq_health_snapshots_prog_date"),)
    program_id: Mapped[uuid.UUID] = _fk("programs")
    date: Mapped[date] = mapped_column(Date)
    score: Mapped[float] = mapped_column(Float)
    subscores: Mapped[dict[str, float]] = mapped_column(JSONB)
    drivers: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)

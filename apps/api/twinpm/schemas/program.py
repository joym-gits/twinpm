"""Program, health, briefing and activity schemas."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel

from twinpm.schemas.common import ORM, Citation, Driver

Severity = Literal["critical", "high", "medium", "low"]


class ProgramOut(ORM):
    id: uuid.UUID
    name: str
    objective: str
    status: str
    target_date: date | None
    owner_user_id: uuid.UUID | None
    health_weights: dict[str, float]


class TrendPoint(BaseModel):
    date: date
    score: float


class HealthDriver(BaseModel):
    subscore: str
    label: str
    value: float | int | None = None


class HealthOut(BaseModel):
    score: float
    delta_7d: float | None
    subscores: dict[str, float]
    trend: list[TrendPoint]
    drivers: list[HealthDriver]
    computed_at: date

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "score": 72.6,
                    "delta_7d": -6.1,
                    "subscores": {
                        "schedule": 70,
                        "scope": 79,
                        "quality": 83,
                        "dependencies": 60,
                        "team": 68,
                    },
                    "trend": [{"date": "2026-11-21", "score": 78.7}],
                    "drivers": [],
                    "computed_at": "2026-11-22",
                }
            ]
        }
    }


class RecommendedAction(BaseModel):
    suggestion_id: uuid.UUID | None
    label: str
    href: str | None = None


class BriefingItem(BaseModel):
    rank: int
    kind: str
    title: str
    why: str
    severity: Severity
    drivers: list[Driver]
    evidence: list[Citation]
    recommended_action: RecommendedAction
    accept_probability: float | None = None


class BriefingOut(BaseModel):
    generated_at: datetime
    items: list[BriefingItem]
    drafted_by: str


class ActivityItem(BaseModel):
    id: int
    actor_type: str
    actor_id: uuid.UUID | None
    actor_name: str | None
    action: str
    entity_type: str
    entity_id: uuid.UUID | None
    summary: str
    reason: str | None
    suggestion_id: uuid.UUID | None
    occurred_at: datetime


class AuditEntry(ORM):
    id: int
    actor_type: str
    actor_id: uuid.UUID | None
    action: str
    entity_type: str
    entity_id: uuid.UUID | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    reason: str | None
    suggestion_id: uuid.UUID | None
    request_id: str | None
    occurred_at: datetime

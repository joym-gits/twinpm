"""Risk, dependency and insight schemas."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from twinpm.schemas.common import ORM, Driver


class RiskyItem(BaseModel):
    work_item_id: uuid.UUID
    key: str
    title: str
    epic: str | None
    team: str | None
    status: str
    owner: str | None
    owner_id: uuid.UUID | None
    due_date: date | None
    probability: float
    drivers: list[Driver]
    model_version: str


class RiskOut(ORM):
    id: uuid.UUID
    program_id: uuid.UUID
    title: str
    description: str
    probability: float
    impact: int
    severity: float
    owner_person_id: uuid.UUID | None
    mitigation: str
    status: str
    source: str
    linked_entities: list[dict[str, Any]]
    created_at: datetime
    updated_at: datetime


class RiskCreate(BaseModel):
    program_id: uuid.UUID
    title: str = Field(min_length=3, max_length=300)
    description: str = ""
    probability: float = Field(ge=0, le=1)
    impact: int = Field(ge=1, le=5)
    owner_person_id: uuid.UUID | None = None
    mitigation: str = ""
    linked_entities: list[dict[str, Any]] = Field(default_factory=list)


class RiskPatch(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=300)
    description: str | None = None
    probability: float | None = Field(default=None, ge=0, le=1)
    impact: int | None = Field(default=None, ge=1, le=5)
    owner_person_id: uuid.UUID | None = None
    mitigation: str | None = None
    status: Literal["open", "mitigating", "closed"] | None = None


class GraphNode(BaseModel):
    id: uuid.UUID
    kind: Literal["epic", "work_item"]
    label: str
    key: str | None
    team_id: uuid.UUID | None
    team: str | None
    status: str
    risk: float
    scope_points: float
    open_items: int
    duration_days: float
    slack_days: float
    critical: bool
    epic_id: uuid.UUID | None = None


class GraphEdge(BaseModel):
    source: uuid.UUID
    target: uuid.UUID
    kind: str
    status: str
    level: str
    critical: bool


class GraphOut(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    critical_path: list[uuid.UUID]
    finish_days: float


class ImpactRequest(BaseModel):
    entity_id: uuid.UUID
    slip_days: int = Field(ge=1, le=120)


class ImpactOut(BaseModel):
    entity_id: uuid.UUID
    slip_days: int
    affected: list[dict[str, Any]]
    baseline_p80: date
    new_p80: date
    delta_days: int
    narrative: str


class MetricPoint(BaseModel):
    date: date
    value: float
    anomaly: bool = False


class MetricSeries(BaseModel):
    team_id: uuid.UUID
    team: str
    metric: str
    points: list[MetricPoint]


class AnomalyOut(ORM):
    id: uuid.UUID
    team_id: uuid.UUID
    metric: str
    date: date
    value: float
    expected: float
    z_score: float
    method: str
    explanation: str
    status: str


class TeamHealthOut(BaseModel):
    team_id: uuid.UUID
    team: str
    size: int
    suppressed: bool
    sentiment_index: float | None
    sentiment_trend: float | None
    after_hours_ratio: float | None
    message_volume: float | None
    utilisation_mean: float | None
    series: list[dict[str, Any]]


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    program_id: uuid.UUID | None = None


class AskOut(BaseModel):
    question: str
    narrative: str
    chart: dict[str, Any]
    citations: list[dict[str, Any]]
    tool_calls: list[dict[str, Any]]

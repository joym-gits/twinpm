"""Roadmap, scenario, forecast and planning schemas."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from twinpm.schemas.common import ORM


class InitiativeCard(BaseModel):
    id: uuid.UUID
    title: str
    description: str
    roadmap_bucket: Literal["now", "next", "later"]
    rice: dict[str, float]
    wsjf: dict[str, float]
    target_date: date | None
    status: str
    objective: str | None
    dependency_count: int
    risk: float
    epics: list[dict[str, Any]]


class RoadmapOut(BaseModel):
    program_id: uuid.UUID
    buckets: dict[str, list[InitiativeCard]]


class InitiativePatch(BaseModel):
    roadmap_bucket: Literal["now", "next", "later"] | None = None
    rice: dict[str, float] | None = None
    wsjf: dict[str, float] | None = None
    reason: str | None = None


class AddScope(BaseModel):
    type: Literal["add_scope"]
    team_id: uuid.UUID
    epic_id: uuid.UUID
    points: float = Field(gt=0, le=500)
    items: int = Field(default=1, ge=1, le=50)


class RemoveScope(BaseModel):
    type: Literal["remove_scope"]
    work_item_ids: list[uuid.UUID] = Field(min_length=1)


class CapacityChange(BaseModel):
    type: Literal["capacity_change"]
    team_id: uuid.UUID
    factor: float = Field(gt=0, le=3)


class Reassign(BaseModel):
    type: Literal["reassign"]
    work_item_ids: list[uuid.UUID] = Field(min_length=1)
    to_person_id: uuid.UUID


class DateShift(BaseModel):
    type: Literal["date_shift"]
    days: int = Field(ge=-120, le=180)


Change = Annotated[
    AddScope | RemoveScope | CapacityChange | Reassign | DateShift, Field(discriminator="type")
]


class SimulateRequest(BaseModel):
    program_id: uuid.UUID
    changes: list[Change] = Field(max_length=50)

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "program_id": "00000000-0000-0000-0000-000000000000",
                    "changes": [
                        {
                            "type": "capacity_change",
                            "team_id": "00000000-0000-0000-0000-000000000001",
                            "factor": 1.2,
                        }
                    ],
                }
            ]
        }
    }


class ForecastBand(BaseModel):
    p50: date
    p80: date
    p95: date
    on_time_probability: float | None = None


class SimulateOut(BaseModel):
    baseline: ForecastBand
    scenario: ForecastBand
    target_date: date | None
    delta_days: int
    risk_delta: float
    capacity_delta: dict[str, float]
    affected_epics: list[dict[str, Any]]
    narrative: str
    histogram: list[dict[str, Any]]
    baseline_histogram: list[dict[str, Any]]


class ScenarioCreate(BaseModel):
    program_id: uuid.UUID
    name: str = Field(min_length=1, max_length=200)
    changes: list[Change]


class ScenarioOut(ORM):
    id: uuid.UUID
    program_id: uuid.UUID
    name: str
    changes: list[dict[str, Any]]
    result: dict[str, Any]
    created_by: uuid.UUID | None
    created_at: datetime


class ForecastOut(BaseModel):
    milestone_id: uuid.UUID
    milestone: str
    target_date: date
    p50: date
    p80: date
    p95: date
    on_time_probability: float | None
    histogram: list[dict[str, Any]]
    epic_p80: dict[str, str]
    assumptions: dict[str, Any]
    run_at: datetime
    previous: ForecastBand | None
    previous_run_at: datetime | None


class BreakdownRequest(BaseModel):
    epic_id: uuid.UUID | None = None
    text: str | None = Field(default=None, max_length=8000)


class ProposedStory(BaseModel):
    title: str
    description: str
    acceptance_criteria: list[str]
    type: str
    story_points: float
    estimate_days: float
    p10_days: float
    p90_days: float
    similar: list[dict[str, Any]]


class BreakdownOut(BaseModel):
    epic_id: uuid.UUID | None
    stories: list[ProposedStory]
    suggestion_ids: list[uuid.UUID]


class SprintPlanRequest(BaseModel):
    team_id: uuid.UUID
    sprint_id: uuid.UUID | None = None


class SprintPlanOut(BaseModel):
    team_id: uuid.UUID
    sprint: str
    capacity_points: float
    pto_points: float
    meeting_points: float
    recommended_commitment: float
    committed_points: float
    stretch: list[dict[str, Any]]
    recommended: list[dict[str, Any]]
    notes: list[str]

"""Delegation schemas."""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel


class PersonLoad(BaseModel):
    person_id: uuid.UUID
    name: str
    title: str
    team_id: uuid.UUID | None
    team: str | None
    utilisation: float
    assigned_points: float
    capacity_points: float
    overloaded: bool
    skills: dict[str, int]
    growth_goals: list[str]
    weeks: list[dict[str, Any]]


class WorkloadOut(BaseModel):
    people: list[PersonLoad]
    weeks: list[str]
    overload_threshold: float
    assignment_counts: dict[str, int]


class CandidateOut(BaseModel):
    person_id: uuid.UUID
    name: str
    team_id: uuid.UUID | None
    score: float
    factors: dict[str, float]
    explanation: str
    utilisation: float


class CandidatesOut(BaseModel):
    work_item_id: uuid.UUID
    key: str
    title: str
    required_skills: dict[str, float]
    weights: dict[str, float]
    candidates: list[CandidateOut]


class RebalanceRequest(BaseModel):
    program_id: uuid.UUID
    scope: list[uuid.UUID] | None = None  # epic IDs; default = critical path


class RebalanceMove(BaseModel):
    work_item_id: uuid.UUID
    key: str
    title: str
    from_person_id: uuid.UUID | None
    from_name: str | None
    to_person_id: uuid.UUID
    to_name: str
    points: float
    risk: float
    explanation: str
    factors: dict[str, float]
    suggestion_id: uuid.UUID | None


class RebalanceOut(BaseModel):
    plan_id: uuid.UUID
    moves: list[RebalanceMove]
    baseline_p80: str
    scenario_p80: str
    delta_days: int
    narrative: str


class NudgeRunOut(BaseModel):
    stalled: int
    suggestions_created: int
    auto_executed: int

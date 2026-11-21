"""Suggestions, persona, autonomy, notifications and integrations schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from twinpm.schemas.common import ORM


class SuggestionOut(ORM):
    id: uuid.UUID
    program_id: uuid.UUID | None
    agent: str
    type: str
    title: str
    payload: dict[str, Any]
    explanation: str
    drivers: list[dict[str, Any]]
    citations: list[dict[str, Any]]
    autonomy_level_required: int
    status: str
    responded_by: uuid.UUID | None
    responded_at: datetime | None
    feedback_reason: str | None
    result: dict[str, Any]
    created_at: datetime
    expires_at: datetime | None
    undone_at: datetime | None
    thread_id: str | None


class RespondRequest(BaseModel):
    action: Literal["accept", "reject", "edit"]
    edited_payload: dict[str, Any] | None = None
    reason: str | None = Field(default=None, max_length=1000)


class PersonaOut(BaseModel):
    user_id: uuid.UUID
    name: str
    priorities: list[str]
    style_examples: list[str]
    tone: Literal["concise", "detailed", "formal", "friendly"]
    risk_tolerance: Literal["low", "medium", "high"]
    escalation_rules: list[dict[str, Any]]
    working_hours: dict[str, Any]
    delegation_weights: dict[str, float]


class PersonaUpdate(BaseModel):
    priorities: list[str] = Field(max_length=12)
    style_examples: list[str] = Field(max_length=10)
    tone: Literal["concise", "detailed", "formal", "friendly"]
    risk_tolerance: Literal["low", "medium", "high"]
    escalation_rules: list[dict[str, Any]] = Field(default_factory=list, max_length=20)
    working_hours: dict[str, Any] = Field(default_factory=dict)


class PolicyEntry(BaseModel):
    action_type: str
    level: int = Field(ge=1, le=4)
    default_level: int
    max_level: int
    description: str


class AutonomyOut(BaseModel):
    program_id: uuid.UUID | None
    policies: list[PolicyEntry]
    levels: dict[int, str]


class AutonomyUpdate(BaseModel):
    program_id: uuid.UUID | None = None
    levels: dict[str, int]


class LearningStats(BaseModel):
    suggestions_seen: int
    acceptance_rate: float | None
    by_type: dict[str, dict[str, float]]
    default_weights: dict[str, float]
    learned_weights: dict[str, float]
    style_examples: int


class NotificationOut(ORM):
    id: uuid.UUID
    kind: str
    title: str
    body: str
    link: str | None
    read_at: datetime | None
    created_at: datetime


class IntegrationOut(ORM):
    id: uuid.UUID
    provider: str
    mode: Literal["mock", "live"]
    last_sync_at: datetime | None
    status: str
    configured: bool = False


class IntegrationPatch(BaseModel):
    mode: Literal["mock", "live"] | None = None
    config: dict[str, Any] | None = None


class SyncOut(BaseModel):
    provider: str
    created: int
    updated: int
    events: int
    details: list[str]

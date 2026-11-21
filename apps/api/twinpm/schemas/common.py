"""Shared API schemas."""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict

CitationType = Literal[
    "work_item",
    "epic",
    "initiative",
    "document",
    "decision",
    "risk",
    "person",
    "team",
    "milestone",
    "forecast",
    "anomaly",
    "metric",
    "feedback",
    "theme",
    "prediction",
    "program",
    "suggestion",
]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Citation(BaseModel):
    type: CitationType
    id: str
    label: str


class Driver(BaseModel):
    feature: str
    value: float | str | None = None
    contribution: float
    label: str


class EntityRef(BaseModel):
    type: CitationType
    id: uuid.UUID

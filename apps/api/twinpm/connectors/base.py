"""Connector interfaces. Mock and live adapters implement these; agents never see vendors."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol


@dataclass(frozen=True)
class WorkItemDTO:
    external_key: str
    title: str
    status: str
    type: str
    story_points: float | None
    assignee_email: str | None
    epic_key: str | None
    updated_at: datetime
    labels: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PullRequestDTO:
    external_id: str
    title: str
    work_item_key: str | None
    state: str  # open | merged | closed
    opened_at: datetime
    first_review_at: datetime | None
    merged_at: datetime | None
    author: str | None


@dataclass(frozen=True)
class ChatMessageDTO:
    channel: str
    text: str
    ts: str
    user: str | None = None


@dataclass(frozen=True)
class CalendarEventDTO:
    title: str
    start: datetime
    end: datetime
    attendees: list[str]


@dataclass(frozen=True)
class DocumentDTO:
    external_id: str
    title: str
    body: str
    url: str | None
    updated_at: datetime


@dataclass
class SyncResult:
    provider: str
    created: int = 0
    updated: int = 0
    events: int = 0
    details: list[str] = field(default_factory=list)


class WorkTrackerConnector(Protocol):
    async def list_work_items(self, since: datetime | None) -> list[WorkItemDTO]: ...


class CodeHostConnector(Protocol):
    async def list_pull_requests(self, since: datetime | None) -> list[PullRequestDTO]: ...


class ChatConnector(Protocol):
    async def post_message(self, channel: str, text: str) -> str: ...

    async def history(self, channel: str, limit: int = 50) -> list[ChatMessageDTO]: ...


class CalendarConnector(Protocol):
    async def upcoming(self, days: int = 7) -> list[CalendarEventDTO]: ...


class DocsConnector(Protocol):
    async def list_documents(self, since: datetime | None) -> list[DocumentDTO]: ...

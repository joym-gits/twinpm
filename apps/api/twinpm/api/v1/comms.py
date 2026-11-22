"""Comms Studio and the decision log."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from twinpm.api.sse import sse
from twinpm.config import get_settings
from twinpm.core import rate_limit
from twinpm.db.models import Document
from twinpm.db.repository import Repo
from twinpm.deps import DB, AiCtx, ProgramWriteCtx, ReadCtx
from twinpm.rag.retrieval import search_decisions
from twinpm.schemas.common import ORM
from twinpm.services import comms

router = APIRouter(tags=["comms"])


class StatusReportRequest(BaseModel):
    program_id: uuid.UUID
    audience: Literal["executive", "engineering", "customer"] = "executive"
    period: str = Field(default="this week", max_length=60)


class ExtractRequest(BaseModel):
    document_id: uuid.UUID | None = None
    transcript_text: str | None = Field(default=None, max_length=50000)


class MeetingPrepRequest(BaseModel):
    meeting_title: str = Field(min_length=3, max_length=200)
    attendee_ids: list[uuid.UUID] = Field(default_factory=list, max_length=20)
    program_id: uuid.UUID


class DecisionOut(ORM):
    id: uuid.UUID
    program_id: uuid.UUID
    title: str
    context: str
    options: list[dict[str, Any]]
    chosen_option: str
    rationale: str
    participants: list[uuid.UUID]
    decided_at: datetime
    source_document_id: uuid.UUID | None


class DecisionCreate(BaseModel):
    program_id: uuid.UUID
    title: str = Field(min_length=3, max_length=300)
    context: str = ""
    options: list[dict[str, Any]] = Field(default_factory=list)
    chosen_option: str = ""
    rationale: str = ""
    participants: list[uuid.UUID] = Field(default_factory=list)
    source_document_id: uuid.UUID | None = None


class DocumentOut(ORM):
    id: uuid.UUID
    type: str
    title: str
    body: str
    occurred_at: datetime | None
    created_at: datetime


async def _ai(ctx: Any) -> None:
    await rate_limit.hit("ai", str(ctx.user_id), get_settings().rate_limit_ai_per_minute)


@router.post(
    "/comms/status-report",
    response_class=EventSourceResponse,
    responses={200: {"content": {"text/event-stream": {}}}},
)
async def status_report(body: StatusReportRequest, ctx: AiCtx, session: DB) -> EventSourceResponse:
    """Streamed status report in the persona's tone; ends with a status_report suggestion."""
    await _ai(ctx)
    return sse(
        comms.status_report_stream(session, ctx, body.program_id, body.audience, body.period)
    )


@router.post("/comms/extract", response_model=comms.ExtractOut)
async def extract(body: ExtractRequest, ctx: AiCtx, session: DB) -> comms.ExtractOut:
    """Decisions and action items from a document or pasted transcript (as suggestions)."""
    await _ai(ctx)
    return await comms.extract(session, ctx, body.document_id, body.transcript_text)


@router.post("/comms/meeting-prep", response_model=dict[str, Any])
async def meeting_prep(body: MeetingPrepRequest, ctx: AiCtx, session: DB) -> dict[str, Any]:
    await _ai(ctx)
    return await comms.meeting_prep(
        session, ctx, body.meeting_title, body.attendee_ids, body.program_id
    )


@router.get("/decisions", response_model=list[DecisionOut])
async def decisions(ctx: ReadCtx, session: DB, q: str | None = None) -> list[DecisionOut]:
    rows = await search_decisions(session, ctx.org_id, q, limit=50)
    return [DecisionOut.model_validate(d) for d, _ in rows]


@router.post("/decisions", response_model=DecisionOut, status_code=201)
async def create_decision(body: DecisionCreate, ctx: ProgramWriteCtx, session: DB) -> DecisionOut:
    return DecisionOut.model_validate(await comms.create_decision(session, ctx, body.model_dump()))


@router.get("/documents", response_model=list[DocumentOut])
async def documents(ctx: ReadCtx, session: DB, type: str | None = None) -> list[DocumentOut]:
    where = [Document.type == type] if type else []
    rows = await Repo(session, ctx, Document).all(*where, order_by=Document.created_at.desc())
    return [DocumentOut.model_validate(d) for d in rows[:100]]


@router.get("/documents/{document_id}", response_model=DocumentOut)
async def document(document_id: uuid.UUID, ctx: ReadCtx, session: DB) -> DocumentOut:
    return DocumentOut.model_validate(await Repo(session, ctx, Document).get(document_id))

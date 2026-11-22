"""Strategy: feedback, themes, PRDs, devil's advocate, OKRs."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Query, UploadFile
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from twinpm.api.sse import sse
from twinpm.config import get_settings
from twinpm.core import rate_limit
from twinpm.core.errors import AppError
from twinpm.db.models import FeedbackItem, Theme
from twinpm.db.repository import Repo
from twinpm.deps import DB, AiCtx, ProgramWriteCtx, ReadCtx
from twinpm.schemas.common import ORM
from twinpm.services import ml_jobs, strategy

router = APIRouter(tags=["strategy"])
MAX_UPLOAD = 5 * 1024 * 1024


class FeedbackOut(ORM):
    id: uuid.UUID
    source: str
    customer_segment: str
    text: str
    sentiment: float
    theme_id: uuid.UUID | None
    received_at: datetime


class ThemeOut(ORM):
    id: uuid.UUID
    label: str
    summary: str
    size: int
    avg_sentiment: float
    opportunity_score: dict[str, Any]
    keywords: list[str]


class PrdRequest(BaseModel):
    idea: str = Field(min_length=3, max_length=500)
    theme_id: uuid.UUID | None = None


class CritiqueRequest(BaseModel):
    document_id: uuid.UUID | None = None
    text: str | None = Field(default=None, max_length=30000)


class OkrRequest(BaseModel):
    program_id: uuid.UUID


async def _ai(ctx: Any) -> None:
    await rate_limit.hit("ai", str(ctx.user_id), get_settings().rate_limit_ai_per_minute)


@router.get("/feedback", response_model=list[FeedbackOut])
async def feedback(
    ctx: ReadCtx,
    session: DB,
    theme_id: uuid.UUID | None = None,
    limit: int = Query(100, ge=1, le=500),
) -> list[FeedbackOut]:
    where = [FeedbackItem.theme_id == theme_id] if theme_id else []
    rows = await Repo(session, ctx, FeedbackItem).all(
        *where, order_by=FeedbackItem.received_at.desc()
    )
    return [FeedbackOut.model_validate(r) for r in rows[:limit]]


@router.post("/feedback/import", response_model=dict[str, int])
async def import_feedback(file: UploadFile, ctx: ProgramWriteCtx, session: DB) -> dict[str, int]:
    raw = await file.read(MAX_UPLOAD + 1)
    if len(raw) > MAX_UPLOAD:
        raise AppError("CSV is larger than 5 MB")
    return {"imported": await strategy.import_feedback(session, ctx, raw)}


@router.post("/strategy/themes/recompute", response_model=dict[str, Any])
async def recompute(ctx: ProgramWriteCtx, session: DB) -> dict[str, Any]:
    """Re-cluster feedback. Enqueued on the worker when available, else run inline."""
    from twinpm.workers.queue import enqueue

    job = await enqueue("recompute_themes", str(ctx.org_id))
    if job:
        return {"status": "queued", "job_id": job}
    return {"status": "done", **await ml_jobs.refresh_themes(session, ctx.org_id)}


@router.get("/strategy/themes", response_model=list[ThemeOut])
async def themes(ctx: ReadCtx, session: DB) -> list[ThemeOut]:
    rows = await Repo(session, ctx, Theme).all()
    rows = sorted(rows, key=lambda t: -float(t.opportunity_score.get("score", 0)))
    return [ThemeOut.model_validate(t) for t in rows]


@router.post(
    "/strategy/prd",
    response_class=EventSourceResponse,
    responses={200: {"content": {"text/event-stream": {}}}},
)
async def prd(body: PrdRequest, ctx: AiCtx, session: DB) -> EventSourceResponse:
    """Streamed PRD markdown, saved as a document."""
    await _ai(ctx)
    return sse(strategy.prd_stream(session, ctx, body.idea, body.theme_id))


@router.post("/strategy/devils-advocate", response_model=dict[str, Any])
async def devils_advocate(body: CritiqueRequest, ctx: AiCtx, session: DB) -> dict[str, Any]:
    await _ai(ctx)
    return await strategy.devils_advocate(session, ctx, body.document_id, body.text)


@router.post("/strategy/okrs/draft", response_model=dict[str, Any])
async def okrs(body: OkrRequest, ctx: AiCtx, session: DB) -> dict[str, Any]:
    await _ai(ctx)
    return await strategy.draft_okrs(session, ctx, body.program_id)

"""Ask the Twin."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from twinpm.api.sse import sse
from twinpm.config import get_settings
from twinpm.core import rate_limit
from twinpm.db.models import Conversation
from twinpm.db.repository import Repo
from twinpm.deps import DB, AiCtx, ReadCtx
from twinpm.schemas.common import ORM
from twinpm.services import chat

router = APIRouter(prefix="/chat", tags=["chat"])


class ConversationCreate(BaseModel):
    program_id: uuid.UUID | None = None
    title: str | None = Field(default=None, max_length=300)


class MessageOut(ORM):
    id: uuid.UUID
    role: str
    content: str
    citations: list[dict[str, Any]]
    tool_calls: list[dict[str, Any]]
    agent_trace: list[dict[str, Any]]
    created_at: datetime


class ConversationOut(ORM):
    id: uuid.UUID
    title: str
    program_id: uuid.UUID | None
    created_at: datetime


class ConversationDetail(BaseModel):
    conversation: ConversationOut
    messages: list[MessageOut]


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    page_context: dict[str, Any] | None = None


@router.post("/conversations", response_model=ConversationOut, status_code=201)
async def create(body: ConversationCreate, ctx: AiCtx, session: DB) -> ConversationOut:
    return ConversationOut.model_validate(
        await chat.create_conversation(session, ctx, body.program_id, body.title)
    )


@router.get("/conversations", response_model=list[ConversationOut])
async def list_conversations(ctx: ReadCtx, session: DB) -> list[ConversationOut]:
    rows = await Repo(session, ctx, Conversation).all(
        Conversation.user_id == ctx.user_id, order_by=Conversation.created_at.desc()
    )
    return [ConversationOut.model_validate(c) for c in rows[:50]]


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
async def get(conversation_id: uuid.UUID, ctx: ReadCtx, session: DB) -> ConversationDetail:
    c, msgs = await chat.get_conversation(session, ctx, conversation_id)
    return ConversationDetail(
        conversation=ConversationOut.model_validate(c),
        messages=[MessageOut.model_validate(x) for x in msgs],
    )


@router.post(
    "/conversations/{conversation_id}/messages",
    response_class=EventSourceResponse,
    responses={200: {"content": {"text/event-stream": {}}}},
)
async def post_message(
    conversation_id: uuid.UUID, body: MessageCreate, ctx: AiCtx, session: DB
) -> EventSourceResponse:
    """SSE: agent_started, tool_call, tool_result, token, citation, approval_required,
    suggestion_created, done, error."""
    await rate_limit.hit("ai", str(ctx.user_id), get_settings().rate_limit_ai_per_minute)
    return sse(chat.stream_message(session, ctx, conversation_id, body.content, body.page_context))

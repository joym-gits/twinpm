"""Server-sent domain events for live UI refresh."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

from twinpm.core.redis import get_redis
from twinpm.deps import ReadCtx
from twinpm.services.events import channel

router = APIRouter(tags=["events"])


@router.get("/events/stream")
async def stream(request: Request, ctx: ReadCtx) -> EventSourceResponse:
    """`event: domain` messages ({kind, data, at}) for the caller's organisation."""

    async def gen() -> AsyncIterator[dict[str, str]]:
        pubsub = get_redis().pubsub()
        await pubsub.subscribe(channel(ctx.org_id))
        try:
            yield {"event": "ready", "data": "{}"}
            while not await request.is_disconnected():
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=15.0)
                if msg is None:
                    yield {"event": "ping", "data": "{}"}
                    continue
                yield {"event": "domain", "data": str(msg["data"])}
                await asyncio.sleep(0)
        finally:
            await pubsub.unsubscribe()
            await pubsub.aclose()  # type: ignore[no-untyped-call]

    return EventSourceResponse(gen(), ping=20)

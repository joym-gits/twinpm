"""Turn `{event, data}` dicts into a server-sent event response."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from sse_starlette.sse import EventSourceResponse


def sse(events: AsyncIterator[dict[str, Any]]) -> EventSourceResponse:
    async def gen() -> AsyncIterator[dict[str, str]]:
        async for ev in events:
            yield {"event": ev["event"], "data": json.dumps(ev.get("data", {}), default=str)}

    return EventSourceResponse(gen(), ping=15)

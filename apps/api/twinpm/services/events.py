"""Domain events over Redis pub/sub. The UI subscribes via SSE `/events/stream`."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from twinpm.core.logging import get_logger
from twinpm.core.redis import get_redis

log = get_logger(__name__)


def channel(org_id: uuid.UUID) -> str:
    return f"twinpm:events:{org_id}"


async def publish(org_id: uuid.UUID, kind: str, data: dict[str, Any] | None = None) -> None:
    from twinpm.services.data_cache import invalidate

    invalidate(org_id)
    msg = {"kind": kind, "data": data or {}, "at": datetime.now(UTC).isoformat()}
    try:
        await get_redis().publish(channel(org_id), json.dumps(msg, default=str))
    except Exception as exc:  # live refresh is best effort; the write already committed
        log.warning("event_publish_failed", kind=kind, error=str(exc))

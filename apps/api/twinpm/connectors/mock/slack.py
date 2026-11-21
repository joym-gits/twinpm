"""Mock Slack: messages land in a Redis-backed channel feed shown in the UI."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

from twinpm.connectors.base import ChatMessageDTO
from twinpm.core.redis import get_redis

FEED_LIMIT = 200


class MockSlack:
    def __init__(self, org_id: uuid.UUID) -> None:
        self.org_id = org_id

    def _key(self, channel: str) -> str:
        return f"twinpm:slack:{self.org_id}:{channel}"

    async def post_message(self, channel: str, text: str) -> str:
        ts = f"{time.time():.6f}"
        msg = {"channel": channel, "text": text, "ts": ts, "user": "TwinPM"}
        r: Any = get_redis()
        await r.lpush(self._key(channel), json.dumps(msg))
        await r.ltrim(self._key(channel), 0, FEED_LIMIT - 1)
        await r.sadd(f"twinpm:slack:{self.org_id}:channels", channel)
        return ts

    async def history(self, channel: str, limit: int = 50) -> list[ChatMessageDTO]:
        r: Any = get_redis()
        raw = await r.lrange(self._key(channel), 0, limit - 1)
        return [ChatMessageDTO(**json.loads(x)) for x in raw]

    async def channels(self) -> list[str]:
        r: Any = get_redis()
        return sorted(await r.smembers(f"twinpm:slack:{self.org_id}:channels"))

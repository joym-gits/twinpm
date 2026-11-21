"""Fixed-window rate limiting in Redis."""

from __future__ import annotations

import time

from twinpm.core.errors import RateLimitedError
from twinpm.core.logging import get_logger
from twinpm.core.redis import get_redis

log = get_logger(__name__)


async def hit(bucket: str, key: str, limit: int, window_seconds: int = 60) -> None:
    window = int(time.time() // window_seconds)
    rkey = f"twinpm:rl:{bucket}:{key}:{window}"
    try:
        r = get_redis()
        count = await r.incr(rkey)
        if count == 1:
            await r.expire(rkey, window_seconds + 1)
    except Exception as exc:  # fail open: an unavailable Redis must not take auth down
        log.warning("rate_limit_unavailable", error=str(exc))
        return
    if count > limit:
        raise RateLimitedError(
            f"Rate limit exceeded for {bucket}", {"limit": limit, "window_seconds": window_seconds}
        )

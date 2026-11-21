"""Shared Redis client."""

from __future__ import annotations

from functools import lru_cache

from redis.asyncio import Redis

from twinpm.config import get_settings


@lru_cache
def get_redis() -> Redis:
    client: Redis = Redis.from_url(get_settings().redis_url, decode_responses=True)
    return client

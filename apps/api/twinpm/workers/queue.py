"""Enqueue ARQ jobs from the API."""

from __future__ import annotations

from typing import Any

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from twinpm.config import get_settings
from twinpm.core.logging import get_logger

log = get_logger(__name__)
_pool: ArqRedis | None = None


async def enqueue(job: str, *args: Any) -> str | None:
    """Return the job id, or None when no worker queue is reachable (caller runs inline)."""
    global _pool
    try:
        if _pool is None:
            _pool = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
        workers = await _pool.get("twinpm:worker:heartbeat")
        if not workers:
            return None
        j = await _pool.enqueue_job(job, *args)
        return j.job_id if j else None
    except Exception as exc:
        log.warning("enqueue_failed", job=job, error=str(exc))
        return None

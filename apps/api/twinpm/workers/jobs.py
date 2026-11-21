"""Background jobs run by the ARQ worker."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

from arq import cron
from arq.typing import WorkerCoroutine

from twinpm.core.redis import get_redis

HEARTBEAT_KEY = "twinpm:worker:heartbeat"


async def heartbeat(_ctx: dict[str, Any]) -> str:
    """Record worker liveness so `/readyz` can report it."""
    now = datetime.now(UTC).isoformat()
    await get_redis().set(HEARTBEAT_KEY, now, ex=180)
    return now


FUNCTIONS: list[Any] = [heartbeat]


def _job(fn: Any) -> WorkerCoroutine:
    return cast(WorkerCoroutine, fn)


CRON_JOBS: list[Any] = [cron(_job(heartbeat), second={0}, run_at_startup=True)]

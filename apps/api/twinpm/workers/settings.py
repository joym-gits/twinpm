"""ARQ worker settings. Jobs and cron schedules are registered in `twinpm.workers.jobs`."""

from __future__ import annotations

from typing import Any, ClassVar

from arq.connections import RedisSettings

from twinpm.config import get_settings
from twinpm.core.logging import configure_logging, get_logger
from twinpm.workers.jobs import CRON_JOBS, FUNCTIONS

log = get_logger("worker")


async def on_startup(_ctx: dict[str, Any]) -> None:
    s = get_settings()
    configure_logging(s.log_level, s.log_json)
    log.info("worker_startup", demo_mode=s.effective_demo_mode)


class WorkerSettings:
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    functions: ClassVar[list[Any]] = FUNCTIONS
    cron_jobs: ClassVar[list[Any]] = CRON_JOBS
    on_startup = on_startup
    max_jobs = 4
    job_timeout = 900

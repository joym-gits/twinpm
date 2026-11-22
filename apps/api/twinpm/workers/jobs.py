"""Background jobs and schedules (ARQ).

- Every 15 minutes (every 2 with DEMO_LIVE_TICKS): connector sync; mock trackers emit ticks.
- Hourly: risk review graph (re-score, forecast, anomalies, health, model risks) and nudges.
- Every half hour: morning briefing for owners whose local time is 07:30.
- Nightly 02:00 UTC: retrain models, backtest the forecaster, recompute themes, prune
  agent checkpoints.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, cast
from zoneinfo import ZoneInfo

from arq import cron
from arq.typing import WorkerCoroutine
from sqlalchemy import select

from twinpm.config import get_settings
from twinpm.core.logging import get_logger
from twinpm.core.redis import get_redis
from twinpm.core.tenancy import TenantContext
from twinpm.db import models as m
from twinpm.db.session import get_sessionmaker

log = get_logger("jobs")
HEARTBEAT_KEY = "twinpm:worker:heartbeat"
BRIEFING_LOCAL_TIME = (7, 30)


async def heartbeat(_ctx: dict[str, Any]) -> str:
    """Record worker liveness so `/readyz` can report it."""
    now = datetime.now(UTC).isoformat()
    await get_redis().set(HEARTBEAT_KEY, now, ex=180)
    return now


async def _org_ids() -> list[uuid.UUID]:
    async with get_sessionmaker()() as s:
        return list((await s.execute(select(m.Organization.id))).scalars())


async def connector_sync(_ctx: dict[str, Any]) -> dict[str, int]:
    from twinpm.connectors.sync import sync_integration

    totals = {"orgs": 0, "events": 0}
    for org_id in await _org_ids():
        async with get_sessionmaker()() as s:
            integs = (
                (
                    await s.execute(
                        select(m.Integration).where(
                            m.Integration.org_id == org_id,
                            m.Integration.provider.in_(["jira", "github"]),
                        )
                    )
                )
                .scalars()
                .all()
            )
            ctx = TenantContext.system(org_id)
            for integ in integs:
                try:
                    res = await sync_integration(s, ctx, integ)
                    totals["events"] += res.events
                except Exception as exc:  # one failing connector must not stop the rest
                    integ.status = f"error: {type(exc).__name__}"
                    log.warning("connector_sync_failed", provider=integ.provider, error=str(exc))
            await s.commit()
        totals["orgs"] += 1
    return totals


async def hourly_review(_ctx: dict[str, Any]) -> dict[str, Any]:
    from twinpm.agents.graphs.background import nudge_graph, owner_state, risk_review_graph

    out: dict[str, Any] = {}
    for org_id in await _org_ids():
        st = await owner_state(org_id)
        if st is None:
            continue
        try:
            r = await risk_review_graph.ainvoke(st)
            n = await nudge_graph.ainvoke(st)
            out[str(org_id)] = {"risk": r["result"], "nudges": n["result"]}
        except Exception as exc:
            log.warning("hourly_review_failed", org_id=str(org_id), error=str(exc))
    return out


def briefing_due(tz: str, now: datetime) -> bool:
    try:
        local = now.astimezone(ZoneInfo(tz))
    except (KeyError, ValueError):
        local = now
    return (local.hour, local.minute // 30 * 30) == BRIEFING_LOCAL_TIME


async def morning_briefing(_ctx: dict[str, Any], force: bool = False) -> int:
    from twinpm.agents.graphs.background import briefing_graph, owner_state

    sent = 0
    now = datetime.now(UTC)
    for org_id in await _org_ids():
        st = await owner_state(org_id)
        if st is None:
            continue
        async with get_sessionmaker()() as s:
            owner = await s.get(m.User, uuid.UUID(st["user_id"]))
        if owner is None or not (force or briefing_due(owner.timezone, now)):
            continue
        try:
            await briefing_graph.ainvoke(st)
            sent += 1
        except Exception as exc:
            log.warning("briefing_failed", org_id=str(org_id), error=str(exc))
    return sent


async def nightly(_ctx: dict[str, Any]) -> dict[str, Any]:
    from twinpm.agents.retention import prune_checkpoints
    from twinpm.ml import backtest
    from twinpm.ml.data import load_program_data
    from twinpm.services import ml_jobs

    out: dict[str, Any] = {"pruned_threads": await prune_checkpoints()}
    for org_id in await _org_ids():
        async with get_sessionmaker()() as s:
            try:
                out[str(org_id)] = await ml_jobs.train_and_refresh(s, org_id)
                program, _ = await ml_jobs.program_context(s, org_id)
                data = await load_program_data(s, org_id, program.id)
                model, _ = ml_jobs.get_models(data)
                bt = backtest.run(data, model, sims=1000)
                out[str(org_id)]["backtest"] = {k: v for k, v in bt.items() if k != "results"}
            except Exception as exc:
                log.warning("nightly_failed", org_id=str(org_id), error=str(exc))
    return out


async def recompute_themes(_ctx: dict[str, Any], org_id: str) -> dict[str, Any]:
    from twinpm.services import ml_jobs

    async with get_sessionmaker()() as s:
        return await ml_jobs.refresh_themes(s, uuid.UUID(org_id))


def _job(fn: Any) -> WorkerCoroutine:
    return cast(WorkerCoroutine, fn)


def _sync_minutes() -> set[int]:
    return set(range(0, 60, 2)) if get_settings().demo_live_ticks else {0, 15, 30, 45}


FUNCTIONS: list[Any] = [
    heartbeat,
    connector_sync,
    hourly_review,
    morning_briefing,
    nightly,
    recompute_themes,
]
CRON_JOBS: list[Any] = [
    cron(_job(heartbeat), second={0}, run_at_startup=True),
    cron(_job(connector_sync), minute=_sync_minutes(), second={5}),
    cron(_job(hourly_review), minute={7}, second={0}),
    cron(_job(morning_briefing), minute={0, 30}, second={30}),
    cron(_job(nightly), hour={2}, minute={0}, second={0}),
]

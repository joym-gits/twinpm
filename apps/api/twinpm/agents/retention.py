"""Prune LangGraph checkpoints for threads idle longer than the retention window."""

from __future__ import annotations

from sqlalchemy import text

from twinpm.db.session import get_sessionmaker

RETENTION_DAYS = 30


async def prune_checkpoints(days: int = RETENTION_DAYS) -> int:
    async with get_sessionmaker()() as s:
        exists = await s.scalar(text("SELECT to_regclass('langgraph.checkpoints') IS NOT NULL"))
        if not exists:
            return 0
        stale = (
            (
                await s.execute(
                    text(
                        "SELECT thread_id FROM langgraph.checkpoints GROUP BY thread_id "
                        "HAVING max((checkpoint->>'ts')::timestamptz) "
                        "< now() - make_interval(days => :d)"
                    ),
                    {"d": days},
                )
            )
            .scalars()
            .all()
        )
        for table in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
            await s.execute(
                text(f"DELETE FROM langgraph.{table} WHERE thread_id = ANY(:ids)"),  # noqa: S608
                {"ids": list(stale)},
            )
        await s.commit()
        return len(stale)

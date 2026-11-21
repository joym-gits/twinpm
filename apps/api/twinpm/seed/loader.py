"""Write a generated Dataset into Postgres, replacing any existing demo org (idempotent)."""

from __future__ import annotations

import time
from typing import Any

from sqlalchemy import delete, insert, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from twinpm.core.security import hash_password
from twinpm.db import models as m
from twinpm.rag.indexer import chunk_rows, embed_feedback_rows
from twinpm.seed.generator import Dataset

ORDER: list[tuple[str, Any]] = [
    ("organizations", m.Organization),
    ("users", m.User),
    ("teams", m.Team),
    ("people", m.Person),
    ("skills", m.Skill),
    ("person_skills", m.PersonSkill),
    ("time_off", m.TimeOff),
    ("programs", m.Program),
    ("objectives", m.Objective),
    ("initiatives", m.Initiative),
    ("epics", m.Epic),
    ("milestones", m.Milestone),
    ("sprints", m.Sprint),
    ("work_items", m.WorkItem),
    ("work_item_events", m.WorkItemEvent),
    ("dependencies", m.Dependency),
    ("metrics_daily", m.MetricDaily),
    ("team_signals", m.TeamSignal),
    ("risks", m.Risk),
    ("health_snapshots", m.HealthSnapshot),
    ("persona_profiles", m.PersonaProfile),
    ("integrations", m.Integration),
    ("documents", m.Document),
    ("document_chunks", m.DocumentChunk),
    ("decisions", m.Decision),
    ("feedback_items", m.FeedbackItem),
]
BATCH = 2000


async def purge_org(session: AsyncSession, slug: str) -> None:
    """Delete a tenant and everything it owns, including its audit trail."""
    org_id = await session.scalar(select(m.Organization.id).where(m.Organization.slug == slug))
    if org_id is None:
        return
    await session.execute(text("SET LOCAL twinpm.audit_purge = 'on'"))
    if await _has_checkpoints(session):
        # Agent threads are keyed "{org_id}:{conversation_id}".
        for table in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
            await session.execute(
                text(f"DELETE FROM langgraph.{table} WHERE thread_id LIKE :p"),  # noqa: S608
                {"p": f"{org_id}:%"},
            )
    # Break the teams <-> people cycle, then let ON DELETE CASCADE do the rest.
    await session.execute(
        update(m.Team).where(m.Team.org_id == org_id).values(manager_person_id=None)
    )
    await session.execute(delete(m.Organization).where(m.Organization.id == org_id))
    await session.execute(text("SET LOCAL twinpm.audit_purge = 'off'"))


async def _has_checkpoints(session: AsyncSession) -> bool:
    return bool(
        await session.scalar(text("SELECT to_regclass('langgraph.checkpoints') IS NOT NULL"))
    )


async def load(session: AsyncSession, ds: Dataset, password: str) -> dict[str, float]:
    t0 = time.perf_counter()
    org = ds.tables["organizations"][0]
    await purge_org(session, org["slug"])
    pw_hash = hash_password(password)
    for u in ds.tables["users"]:
        u["password_hash"] = pw_hash
    managers = {t["id"]: t["manager_person_id"] for t in ds.tables["teams"]}
    tables = dict(ds.tables)
    tables["teams"] = [{**t, "manager_person_id": None} for t in ds.tables["teams"]]
    tables["document_chunks"] = chunk_rows(ds.tables["documents"])
    tables["feedback_items"] = embed_feedback_rows(ds.tables["feedback_items"])
    for name, model in ORDER:
        rows = tables.get(name, [])
        for i in range(0, len(rows), BATCH):
            await session.execute(insert(model), rows[i : i + BATCH])
        if name == "people":
            for tid, pid in managers.items():
                await session.execute(
                    update(m.Team).where(m.Team.id == tid).values(manager_person_id=pid)
                )
    await session.commit()
    return {"seconds": round(time.perf_counter() - t0, 2)}

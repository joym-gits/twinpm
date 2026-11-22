"""Mock Jira/GitHub: replays seed state and, with DEMO_LIVE_TICKS, emits small realistic changes.

Each tick moves a few in-flight items forward (in progress -> in review -> done), records PR
reviews and comments, exactly as a webhook-driven sync from a live tracker would.
"""

from __future__ import annotations

import random
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from twinpm.connectors.base import SyncResult
from twinpm.db import models as m

NEXT_STATUS = {
    "todo": "in_progress",
    "in_progress": "in_review",
    "blocked": "in_progress",
    "in_review": "done",
}


async def tick(
    session: AsyncSession, org_id: uuid.UUID, provider: str, n: int = 3, seed: int | None = None
) -> SyncResult:
    rng = random.Random(seed)
    res = SyncResult(provider)
    now = datetime.now(UTC)
    items = (
        (
            await session.execute(
                select(m.WorkItem).where(
                    m.WorkItem.org_id == org_id,
                    m.WorkItem.status.in_(list(NEXT_STATUS)),
                    m.WorkItem.started_at.is_not(None),
                    m.WorkItem.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    if not items:
        return res
    for item in rng.sample(list(items), min(n, len(items))):
        if provider == "github":
            hours = round(rng.uniform(2, 20), 1)
            item.pr_review_hours += hours
            session.add(
                m.WorkItemEvent(
                    org_id=org_id,
                    work_item_id=item.id,
                    event_type="pr_reviewed",
                    to_value=str(hours),
                    actor_person_id=item.assignee_person_id,
                    occurred_at=now,
                )
            )
            res.events += 1
            res.details.append(f"{item.key}: PR reviewed after {hours}h")
            continue
        if rng.random() < 0.4:
            item.comments_count += 1
            session.add(
                m.WorkItemEvent(
                    org_id=org_id,
                    work_item_id=item.id,
                    event_type="comment",
                    actor_person_id=item.assignee_person_id,
                    occurred_at=now,
                )
            )
            res.events += 1
            res.details.append(f"{item.key}: new comment")
            continue
        new = NEXT_STATUS[item.status]
        session.add(
            m.WorkItemEvent(
                org_id=org_id,
                work_item_id=item.id,
                event_type="status_change",
                from_value=item.status,
                to_value=new,
                actor_person_id=item.assignee_person_id,
                occurred_at=now,
            )
        )
        res.details.append(f"{item.key}: {item.status} -> {new}")
        item.status = new
        if new == "done":
            item.done_at = now
        res.updated += 1
        res.events += 1
    return res

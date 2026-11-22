"""Idempotent upserts from connector DTOs into domain tables, keyed by external_ref."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from twinpm.connectors.base import PullRequestDTO, SyncResult, WorkItemDTO
from twinpm.core.tenancy import TenantContext
from twinpm.db import models as m


async def upsert_work_items(
    session: AsyncSession, ctx: TenantContext, items: list[WorkItemDTO]
) -> SyncResult:
    res = SyncResult("jira")
    people = {
        u.email: p.id
        for u, p in (
            await session.execute(
                select(m.User, m.Person)
                .join(m.Person, m.Person.user_id == m.User.id)
                .where(m.User.org_id == ctx.org_id)
            )
        ).all()
    }
    for dto in items:
        row = (
            await session.execute(
                select(m.WorkItem).where(
                    m.WorkItem.org_id == ctx.org_id, m.WorkItem.key == dto.external_key
                )
            )
        ).scalar()
        assignee = people.get(dto.assignee_email or "")
        if row is None:
            session.add(
                m.WorkItem(
                    org_id=ctx.org_id,
                    key=dto.external_key,
                    title=dto.title,
                    type=dto.type,
                    status=dto.status,
                    story_points=dto.story_points or 0,
                    assignee_person_id=assignee,
                    created_at_src=dto.updated_at,
                    labels=dto.labels,
                    external_ref={"provider": "jira", "key": dto.external_key, **dto.raw},
                )
            )
            res.created += 1
            continue
        if row.status != dto.status:
            session.add(
                m.WorkItemEvent(
                    org_id=ctx.org_id,
                    work_item_id=row.id,
                    event_type="status_change",
                    from_value=row.status,
                    to_value=dto.status,
                    occurred_at=dto.updated_at,
                )
            )
            res.events += 1
            if dto.status == "done" and row.done_at is None:
                row.done_at = dto.updated_at
        row.title, row.status, row.labels = dto.title, dto.status, dto.labels
        if dto.story_points is not None:
            row.story_points = dto.story_points
        if assignee:
            row.assignee_person_id = assignee
        res.updated += 1
    return res


async def apply_pull_requests(
    session: AsyncSession, ctx: TenantContext, prs: list[PullRequestDTO]
) -> SyncResult:
    res = SyncResult("github")
    for pr in prs:
        if not pr.work_item_key:
            continue
        item = (
            await session.execute(
                select(m.WorkItem).where(
                    m.WorkItem.org_id == ctx.org_id, m.WorkItem.key == pr.work_item_key
                )
            )
        ).scalar()
        if item is None:
            continue
        seen = (item.external_ref or {}).get("prs", [])
        if pr.external_id in seen:
            continue  # idempotent: each PR is applied once
        waited = ((pr.first_review_at or datetime.now(UTC)) - pr.opened_at).total_seconds() / 3600
        item.pr_review_hours += round(max(waited, 0.0), 1)
        item.external_ref = {**(item.external_ref or {}), "prs": [*seen, pr.external_id]}
        session.add(
            m.WorkItemEvent(
                org_id=ctx.org_id,
                work_item_id=item.id,
                event_type="pr_opened",
                occurred_at=pr.opened_at,
            )
        )
        if pr.first_review_at:
            session.add(
                m.WorkItemEvent(
                    org_id=ctx.org_id,
                    work_item_id=item.id,
                    event_type="pr_reviewed",
                    to_value=f"{waited:.1f}",
                    occurred_at=pr.first_review_at,
                )
            )
        res.updated += 1
        res.events += 1 + int(pr.first_review_at is not None)
    return res

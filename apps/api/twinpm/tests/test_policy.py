"""The autonomy policy is deterministic and the twin cannot raise its own permissions."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from twinpm.core.errors import PolicyViolationError
from twinpm.db import models as m
from twinpm.services import actions, policy, suggestions
from twinpm.tests.factories import make_org


async def _team_item(db: AsyncSession, org_id: uuid.UUID) -> tuple[m.WorkItem, m.Person]:
    from datetime import UTC, datetime

    team = m.Team(org_id=org_id, name="T")
    db.add(team)
    await db.flush()
    a = m.Person(org_id=org_id, name="A", title="Eng", team_id=team.id, growth_goals=[])
    b = m.Person(org_id=org_id, name="B", title="Eng", team_id=team.id, growth_goals=[])
    db.add_all([a, b])
    await db.flush()
    item = m.WorkItem(
        org_id=org_id,
        team_id=team.id,
        key=f"T-{uuid.uuid4().hex[:4]}",
        title="x",
        type="task",
        status="todo",
        story_points=1,
        assignee_person_id=a.id,
        created_at_src=datetime.now(UTC),
        labels=[],
        external_ref={},
    )
    db.add(item)
    await db.flush()
    return item, b


def test_defaults_and_ceilings() -> None:
    assert policy.DEFAULTS["roadmap_change"] == policy.Level.SUGGEST
    assert policy.DEFAULTS["reassign"] == policy.Level.APPROVE
    assert policy.DEFAULTS["nudge"] == policy.Level.APPROVE
    assert policy.DEFAULTS["alert"] == policy.Level.AUTONOMOUS
    assert policy.ceiling("status_report") == policy.Level.APPROVE
    d = policy.decide("reassign", policy.Level.APPROVE)
    assert d.create_suggestion and not d.execute_now and not d.notify_only
    assert policy.decide("x", policy.Level.OBSERVE).notify_only


async def test_twin_cannot_execute_above_its_level(db: AsyncSession) -> None:
    o = await make_org(db)
    item, b = await _team_item(db, o.org.id)
    twin = o.ctx("tpm").as_twin()
    payload = {"work_item_ids": [str(item.id)], "to_person_id": str(b.id)}
    with pytest.raises(PolicyViolationError):
        await actions.execute(db, twin, "reassign", payload)
    # A payload that claims a higher level changes nothing: the engine reads policy rows only.
    sneaky = {**payload, "autonomy_level_required": 4, "level": 4}
    s = await suggestions.create(
        db, o.ctx("tpm"), type="reassign", title="Move it", payload=sneaky, agent="delegation"
    )
    assert s is not None
    assert s.status == "pending"
    assert s.autonomy_level_required == 3
    await db.rollback()


async def test_policy_rows_drive_behaviour(db: AsyncSession) -> None:
    o = await make_org(db)
    item, b = await _team_item(db, o.org.id)
    ctx = o.ctx("tpm")
    db.add(m.AutonomyPolicy(org_id=o.org.id, user_id=ctx.user_id, action_type="reassign", level=4))
    await db.flush()
    s = await suggestions.create(
        db,
        ctx,
        type="reassign",
        title="Move it",
        agent="delegation",
        payload={"work_item_ids": [str(item.id)], "to_person_id": str(b.id)},
    )
    assert s is not None and s.status == "auto_executed"
    await db.refresh(item)
    assert item.assignee_person_id == b.id
    audit = (
        (await db.execute(select(m.AuditLog).where(m.AuditLog.entity_id == item.id)))
        .scalars()
        .all()
    )
    assert any(a.actor_type == "twin" and a.action == "work_item.reassigned" for a in audit)
    db.add(m.AutonomyPolicy(org_id=o.org.id, user_id=ctx.user_id, action_type="alert", level=1))
    await db.flush()
    none = await suggestions.create(
        db, ctx, type="alert", title="FYI", agent="risk", payload={"title": "FYI"}
    )
    assert none is None
    await db.rollback()


async def test_status_report_ceiling_cannot_be_bypassed(db: AsyncSession) -> None:
    o = await make_org(db)
    ctx = o.ctx("tpm")
    db.add(
        m.AutonomyPolicy(org_id=o.org.id, user_id=ctx.user_id, action_type="status_report", level=4)
    )
    await db.flush()
    level = await policy.level_for(db, o.org.id, ctx.user_id, "status_report")
    assert level == policy.Level.APPROVE
    await db.rollback()


async def test_rbac_applies_to_executor(db: AsyncSession) -> None:
    from twinpm.core.errors import ForbiddenError

    o = await make_org(db)
    item, b = await _team_item(db, o.org.id)
    with pytest.raises(ForbiddenError):
        await actions.execute(
            db,
            o.ctx("viewer"),
            "reassign",
            {"work_item_ids": [str(item.id)], "to_person_id": str(b.id)},
        )
    await db.rollback()

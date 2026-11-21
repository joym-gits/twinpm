"""The audit log is append-only at the database level."""

from __future__ import annotations

import pytest
from sqlalchemy import delete, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from twinpm.db.models import AuditLog
from twinpm.services import audit
from twinpm.tests.factories import make_org


async def test_audit_rows_cannot_be_updated_or_deleted(db: AsyncSession) -> None:
    o = await make_org(db)
    entry = await audit.record(
        db, o.ctx(), action="test.created", entity_type="program", entity_id=o.program.id,
        after={"x": 1},
    )
    await db.commit()
    entry_id, program_id = entry.id, o.program.id
    ctx = o.ctx()
    with pytest.raises(DBAPIError, match="append-only"):
        await db.execute(update(AuditLog).where(AuditLog.id == entry_id).values(action="tampered"))
    await db.rollback()
    with pytest.raises(DBAPIError, match="append-only"):
        await db.execute(delete(AuditLog).where(AuditLog.id == entry_id))
    await db.rollback()
    with pytest.raises(DBAPIError, match="append-only"):
        await db.execute(text("TRUNCATE audit_log"))
    await db.rollback()
    rows = await audit.query(db, ctx, entity_id=program_id)
    assert [r.action for r in rows] == ["test.created"]


async def test_audit_query_is_tenant_scoped(db: AsyncSession) -> None:
    a = await make_org(db)
    b = await make_org(db)
    await audit.record(db, b.ctx(), action="b.only", entity_type="program", entity_id=b.program.id)
    await db.commit()
    assert await audit.query(db, a.ctx(), entity_id=b.program.id) == []

"""Cross-tenant reads and writes must be impossible through the repository layer."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from twinpm.core.errors import NotFoundError
from twinpm.db.models import Program, Team
from twinpm.db.repository import Repo
from twinpm.tests.factories import make_org


async def test_cross_tenant_reads_are_impossible(db: AsyncSession) -> None:
    a = await make_org(db)
    b = await make_org(db)
    db.add(Team(org_id=b.org.id, name="B secret team"))
    await db.commit()

    repo_a = Repo(db, a.ctx(), Program)
    assert await repo_a.get_or_none(b.program.id) is None
    with pytest.raises(NotFoundError):
        await repo_a.get(b.program.id)
    ids = {p.id for p in await repo_a.all()}
    assert ids == {a.program.id}
    page = await Repo(db, a.ctx(), Team).page(limit=100)
    assert all(t.org_id == a.org.id for t in page.items)
    assert "B secret team" not in {t.name for t in page.items}


async def test_cross_tenant_writes_are_refused(db: AsyncSession) -> None:
    a = await make_org(db)
    b = await make_org(db)
    repo_a = Repo(db, a.ctx(), Team)
    with pytest.raises(PermissionError):
        repo_a.add(Team(org_id=b.org.id, name="smuggled"))
    with pytest.raises(PermissionError):
        await repo_a.soft_delete(Team(org_id=b.org.id, name="x"))  # type: ignore[arg-type]


async def test_add_stamps_org_and_soft_delete_hides(db: AsyncSession) -> None:
    a = await make_org(db)
    repo = Repo(db, a.ctx(), Team)
    t = repo.add(Team(name="Platform"))
    await db.flush()
    assert t.org_id == a.org.id
    await repo.soft_delete(t)
    await db.flush()
    assert await repo.get_or_none(t.id) is None


async def test_repo_rejects_untenanted_models(db: AsyncSession) -> None:
    from twinpm.db.models import Organization

    a = await make_org(db)
    with pytest.raises(TypeError):
        Repo(db, a.ctx(), Organization)

"""Tenant-scoped repository layer.

All reads and writes of tenant-owned tables go through `Repo`, which always filters by the
authenticated `org_id` and hides soft-deleted rows. Services never build unscoped queries
against tenant tables.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, cast

from sqlalchemy import Select, and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from twinpm.core.errors import NotFoundError
from twinpm.core.pagination import decode_cursor, encode_cursor
from twinpm.core.tenancy import TenantContext
from twinpm.db.base import Base


@dataclass
class RowPage[T]:
    items: list[T]
    next_cursor: str | None


class Repo[M: Base]:
    def __init__(self, session: AsyncSession, ctx: TenantContext, model: type[M]) -> None:
        if not hasattr(model, "org_id"):
            raise TypeError(f"{model.__name__} is not tenant-scoped")
        self.session = session
        self.ctx = ctx
        self.model = model

    def _scope(self) -> list[ColumnElement[bool]]:
        m: Any = self.model
        conds: list[ColumnElement[bool]] = [m.org_id == self.ctx.org_id]
        if hasattr(m, "deleted_at"):
            conds.append(m.deleted_at.is_(None))
        return conds

    def select(self, *where: ColumnElement[bool]) -> Select[M]:
        return select(self.model).where(*self._scope(), *where)

    async def get_or_none(self, id_: uuid.UUID) -> M | None:
        m: Any = self.model
        res = await self.session.execute(self.select(m.id == id_))
        return res.scalar_one_or_none()

    async def get(self, id_: uuid.UUID) -> M:
        obj = await self.get_or_none(id_)
        if obj is None:
            raise NotFoundError(f"{self.model.__name__} {id_} not found")
        return obj

    async def all(self, *where: ColumnElement[bool], order_by: Any = None) -> Sequence[M]:
        stmt = self.select(*where)
        if order_by is not None:
            stmt = stmt.order_by(order_by)
        return (await self.session.execute(stmt)).scalars().all()

    async def page(
        self,
        *where: ColumnElement[bool],
        limit: int = 50,
        cursor: str | None = None,
        newest_first: bool = True,
    ) -> RowPage[M]:
        m: Any = self.model
        stmt = self.select(*where)
        if cursor:
            ts, cid = decode_cursor(cursor)
            if newest_first:
                stmt = stmt.where(or_(m.created_at < ts, and_(m.created_at == ts, m.id < cid)))
            else:
                stmt = stmt.where(or_(m.created_at > ts, and_(m.created_at == ts, m.id > cid)))
        order = (m.created_at.desc(), m.id.desc()) if newest_first else (m.created_at, m.id)
        rows = list((await self.session.execute(stmt.order_by(*order).limit(limit + 1))).scalars())
        nxt = None
        if len(rows) > limit:
            last = cast(Any, rows[limit - 1])
            nxt = encode_cursor(last.created_at, last.id)
            rows = rows[:limit]
        return RowPage(items=rows, next_cursor=nxt)

    def add(self, obj: M) -> M:
        o: Any = obj
        if getattr(o, "org_id", None) not in (None, self.ctx.org_id):
            raise PermissionError("Refusing to write a row for another tenant")
        o.org_id = self.ctx.org_id
        self.session.add(obj)
        return obj

    async def soft_delete(self, obj: M) -> None:
        from datetime import UTC, datetime

        o: Any = obj
        if o.org_id != self.ctx.org_id:
            raise PermissionError("Refusing to delete a row for another tenant")
        if hasattr(o, "deleted_at"):
            o.deleted_at = datetime.now(UTC)
        else:
            await self.session.delete(obj)

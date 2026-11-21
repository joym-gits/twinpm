"""`python -m twinpm.ml.train_all`: train every model and refresh all ML outputs."""

from __future__ import annotations

import asyncio
import json

from sqlalchemy import select
from sqlalchemy.exc import NoResultFound

from twinpm.db.models import Organization
from twinpm.db.session import get_engine, get_sessionmaker
from twinpm.services.ml_jobs import train_and_refresh


async def main() -> None:
    async with get_sessionmaker()() as session:
        org_ids = (await session.execute(select(Organization.id))).scalars().all()
        for org_id in org_ids:
            try:
                summary = await train_and_refresh(session, org_id)
            except NoResultFound:
                await session.rollback()
                print(f"skip org {org_id}: no program with a milestone")
                continue
            print(json.dumps({"org_id": str(org_id), **summary}, indent=2, default=str))
    await get_engine().dispose()


if __name__ == "__main__":
    asyncio.run(main())

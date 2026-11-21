"""Short-lived per-process cache of ProgramData, invalidated by domain events."""

from __future__ import annotations

import time
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from twinpm.ml.data import ProgramData, load_program_data

TTL_SECONDS = 60.0
_cache: dict[tuple[uuid.UUID, uuid.UUID | None], tuple[float, ProgramData]] = {}


async def get_program_data(
    session: AsyncSession, org_id: uuid.UUID, program_id: uuid.UUID | None
) -> ProgramData:
    key = (org_id, program_id)
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < TTL_SECONDS:
        return hit[1]
    data = await load_program_data(session, org_id, program_id)
    _cache[key] = (time.monotonic(), data)
    return data


def invalidate(org_id: uuid.UUID) -> None:
    for key in [k for k in _cache if k[0] == org_id]:
        _cache.pop(key, None)

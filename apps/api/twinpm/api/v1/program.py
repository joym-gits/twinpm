"""Programs and the Command Center."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query

from twinpm.db.models import Program
from twinpm.db.repository import Repo
from twinpm.deps import DB, ReadCtx
from twinpm.schemas.program import ActivityItem, BriefingOut, HealthOut, ProgramOut
from twinpm.services import program as svc

router = APIRouter(tags=["program"])


@router.get("/programs", response_model=list[ProgramOut])
async def list_programs(ctx: ReadCtx, session: DB) -> list[ProgramOut]:
    return [
        ProgramOut.model_validate(p)
        for p in await Repo(session, ctx, Program).all(order_by=Program.created_at)
    ]


@router.get("/programs/{program_id}", response_model=ProgramOut)
async def get_program(program_id: uuid.UUID, ctx: ReadCtx, session: DB) -> ProgramOut:
    return ProgramOut.model_validate(await svc.get_program(session, ctx, program_id))


@router.get("/programs/{program_id}/health", response_model=HealthOut)
async def program_health(program_id: uuid.UUID, ctx: ReadCtx, session: DB) -> HealthOut:
    """Health score, five sub-scores, a 30-day trend and the drivers behind it."""
    return await svc.health(session, ctx, program_id)


@router.get("/programs/{program_id}/briefing", response_model=BriefingOut)
async def program_briefing(
    program_id: uuid.UUID, ctx: ReadCtx, session: DB, refresh: bool = False
) -> BriefingOut:
    """Top three attention items, ranked by severity and the TPM's learned preferences."""
    return await svc.briefing(session, ctx, program_id, refresh)


@router.get("/programs/{program_id}/activity", response_model=list[ActivityItem])
async def program_activity(
    program_id: uuid.UUID, ctx: ReadCtx, session: DB, limit: int = Query(50, ge=1, le=200)
) -> list[ActivityItem]:
    await svc.get_program(session, ctx, program_id)
    return await svc.activity(session, ctx, limit)

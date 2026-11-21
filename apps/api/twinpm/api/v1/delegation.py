"""Delegation board."""

from __future__ import annotations

import uuid

from fastapi import APIRouter

from twinpm.deps import DB, ProgramWriteCtx, ReadCtx
from twinpm.schemas.delegation import (
    CandidatesOut,
    NudgeRunOut,
    RebalanceOut,
    RebalanceRequest,
    WorkloadOut,
)
from twinpm.services import delegation as svc

router = APIRouter(prefix="/delegation", tags=["delegation"])


@router.get("/workload", response_model=WorkloadOut)
async def workload(program_id: uuid.UUID, ctx: ReadCtx, session: DB) -> WorkloadOut:
    """Per-person utilisation (team-level work signals only), weekly heatmap and overload flags."""
    return await svc.workload(session, ctx, program_id)


@router.get("/candidates/{work_item_id}", response_model=CandidatesOut)
async def candidates(work_item_id: uuid.UUID, ctx: ReadCtx, session: DB) -> CandidatesOut:
    return await svc.candidates(session, ctx, work_item_id)


@router.post("/rebalance", response_model=RebalanceOut)
async def rebalance(body: RebalanceRequest, ctx: ProgramWriteCtx, session: DB) -> RebalanceOut:
    """Plan reassignments off the critical path; each move becomes a suggestion."""
    return await svc.rebalance(session, ctx, body.program_id, body.scope)


@router.post("/nudges/run", response_model=NudgeRunOut)
async def run_nudges(program_id: uuid.UUID, ctx: ProgramWriteCtx, session: DB) -> NudgeRunOut:
    return await svc.run_nudges(session, ctx, program_id)

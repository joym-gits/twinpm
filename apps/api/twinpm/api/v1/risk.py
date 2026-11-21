"""Risk radar and dependencies."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query

from twinpm.db.models import Risk
from twinpm.db.repository import Repo
from twinpm.deps import DB, ReadCtx, RiskWriteCtx
from twinpm.schemas.risk import (
    GraphOut,
    ImpactOut,
    ImpactRequest,
    RiskCreate,
    RiskOut,
    RiskPatch,
    RiskyItem,
)
from twinpm.services import risk as svc

router = APIRouter(tags=["risk"])


@router.get("/risk/work-items", response_model=list[RiskyItem])
async def risky_items(
    program_id: uuid.UUID,
    ctx: ReadCtx,
    session: DB,
    min_score: float = Query(0.0, ge=0, le=1),
    limit: int = Query(100, ge=1, le=500),
) -> list[RiskyItem]:
    """Open items with delay probability and SHAP drivers, highest risk first."""
    return await svc.risky_items(session, ctx, program_id, min_score, limit)


@router.get("/risk/register", response_model=list[RiskOut])
async def register(program_id: uuid.UUID, ctx: ReadCtx, session: DB) -> list[RiskOut]:
    rows = await Repo(session, ctx, Risk).all(
        Risk.program_id == program_id, order_by=Risk.severity.desc()
    )
    return [RiskOut.model_validate(r) for r in rows]


@router.post("/risk/register", response_model=RiskOut, status_code=201)
async def create_risk(body: RiskCreate, ctx: RiskWriteCtx, session: DB) -> RiskOut:
    return RiskOut.model_validate(await svc.create_risk(session, ctx, body.model_dump()))


@router.patch("/risk/register/{risk_id}", response_model=RiskOut)
async def update_risk(
    risk_id: uuid.UUID, body: RiskPatch, ctx: RiskWriteCtx, session: DB
) -> RiskOut:
    return RiskOut.model_validate(
        await svc.update_risk(session, ctx, risk_id, body.model_dump(exclude_none=True))
    )


@router.get("/dependencies/graph", response_model=GraphOut)
async def graph(program_id: uuid.UUID, ctx: ReadCtx, session: DB) -> GraphOut:
    """Epics and dependent items with team, status, risk, critical-path flags and slack."""
    return await svc.dependency_graph(session, ctx, program_id)


@router.post("/dependencies/impact", response_model=ImpactOut)
async def impact(body: ImpactRequest, ctx: ReadCtx, session: DB) -> ImpactOut:
    """Cascade of an N-day slip on an epic or work item, with the new launch forecast."""
    return await svc.impact(session, ctx, body.entity_id, body.slip_days)

"""Roadmap, scenarios, forecasts and planning."""

from __future__ import annotations

import uuid

from fastapi import APIRouter

from twinpm.core import rate_limit
from twinpm.db.models import Scenario
from twinpm.db.repository import Repo
from twinpm.deps import DB, AiCtx, ProgramWriteCtx, ReadCtx
from twinpm.schemas.planning import (
    BreakdownOut,
    BreakdownRequest,
    ForecastOut,
    InitiativePatch,
    RoadmapOut,
    ScenarioCreate,
    ScenarioOut,
    SimulateOut,
    SimulateRequest,
    SprintPlanOut,
    SprintPlanRequest,
)
from twinpm.services import planning as svc

router = APIRouter(tags=["planning"])


@router.get("/roadmap", response_model=RoadmapOut)
async def get_roadmap(program_id: uuid.UUID, ctx: ReadCtx, session: DB) -> RoadmapOut:
    return await svc.roadmap(session, ctx, program_id)


@router.patch("/initiatives/{initiative_id}", response_model=dict[str, object])
async def patch_initiative(
    initiative_id: uuid.UUID, body: InitiativePatch, ctx: ProgramWriteCtx, session: DB
) -> dict[str, object]:
    """Move an initiative between buckets or rescore it. Every change is audited."""
    changes = body.model_dump(exclude_none=True, exclude={"reason"})
    return await svc.patch_initiative(session, ctx, initiative_id, changes, body.reason)


@router.post("/scenarios/simulate", response_model=SimulateOut)
async def simulate(body: SimulateRequest, ctx: ReadCtx, session: DB) -> SimulateOut:
    """Run the Monte Carlo forecast with what-if changes (10,000 simulations)."""
    return await svc.simulate(
        session, ctx, body.program_id, [c.model_dump(mode="json") for c in body.changes]
    )


@router.post("/scenarios", response_model=ScenarioOut, status_code=201)
async def save_scenario(body: ScenarioCreate, ctx: ProgramWriteCtx, session: DB) -> ScenarioOut:
    row = await svc.save_scenario(
        session, ctx, body.program_id, body.name, [c.model_dump(mode="json") for c in body.changes]
    )
    return ScenarioOut.model_validate(row)


@router.get("/scenarios", response_model=list[ScenarioOut])
async def list_scenarios(
    ctx: ReadCtx, session: DB, program_id: uuid.UUID | None = None
) -> list[ScenarioOut]:
    where = [Scenario.program_id == program_id] if program_id else []
    rows = await Repo(session, ctx, Scenario).all(*where, order_by=Scenario.created_at.desc())
    return [ScenarioOut.model_validate(r) for r in rows]


@router.get("/forecasts/{milestone_id}", response_model=ForecastOut)
async def get_forecast(milestone_id: uuid.UUID, ctx: ReadCtx, session: DB) -> ForecastOut:
    return await svc.get_forecast(session, ctx, milestone_id)


@router.post("/forecasts/{milestone_id}/run", response_model=ForecastOut)
async def run_forecast(milestone_id: uuid.UUID, ctx: ProgramWriteCtx, session: DB) -> ForecastOut:
    await svc.run_forecast(session, ctx, milestone_id)
    return await svc.get_forecast(session, ctx, milestone_id)


@router.post("/planning/breakdown", response_model=BreakdownOut)
async def breakdown(body: BreakdownRequest, ctx: AiCtx, session: DB) -> BreakdownOut:
    """Propose stories with acceptance criteria and ML estimates (as create_task suggestions)."""
    from twinpm.config import get_settings

    await rate_limit.hit("ai", str(ctx.user_id), get_settings().rate_limit_ai_per_minute)
    return await svc.breakdown(session, ctx, body.epic_id, body.text)


@router.post("/planning/sprint-plan", response_model=SprintPlanOut)
async def sprint_plan(body: SprintPlanRequest, ctx: ReadCtx, session: DB) -> SprintPlanOut:
    return await svc.sprint_plan(session, ctx, body.team_id, body.sprint_id)

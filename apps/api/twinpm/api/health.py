"""Liveness, readiness and Prometheus metrics."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Response
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel
from sqlalchemy import text

from twinpm.core.redis import get_redis
from twinpm.db.session import get_engine
from twinpm.ml.registry import ModelRegistry

router = APIRouter(tags=["platform"])


class Liveness(BaseModel):
    status: Literal["ok"] = "ok"


class Readiness(BaseModel):
    status: Literal["ok", "degraded"]
    checks: dict[str, str]


@router.get("/healthz", response_model=Liveness)
async def healthz() -> Liveness:
    return Liveness()


@router.get("/readyz", response_model=Readiness, responses={503: {"model": Readiness}})
async def readyz() -> Response:
    checks: dict[str, str] = {}
    try:
        async with get_engine().connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:  # readiness must report, not raise
        checks["database"] = f"error: {type(exc).__name__}"
    try:
        await get_redis().ping()
        checks["redis"] = "ok"
    except Exception as exc:
        checks["redis"] = f"error: {type(exc).__name__}"
    try:
        from twinpm.workers.jobs import HEARTBEAT_KEY

        checks["worker"] = "ok" if await get_redis().get(HEARTBEAT_KEY) else "no heartbeat"
    except Exception as exc:
        checks["worker"] = f"error: {type(exc).__name__}"
    checks["model_registry"] = "ok" if ModelRegistry.default().is_ready() else "untrained"
    # Untrained models degrade AI features but do not block serving.
    ok = checks["database"] == "ok" and checks["redis"] == "ok"
    body = Readiness(status="ok" if ok else "degraded", checks=checks)
    return JSONResponse(status_code=200 if ok else 503, content=body.model_dump())


@router.get("/metrics", include_in_schema=False)
async def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

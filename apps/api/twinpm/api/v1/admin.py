"""Admin: AI usage telemetry."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter
from sqlalchemy import func, select

from twinpm.db.models import LlmCall
from twinpm.deps import DB, AdminCtx

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/ai-usage", response_model=dict[str, Any])
async def ai_usage(ctx: AdminCtx, session: DB, days: int = 30) -> dict[str, Any]:
    since = datetime.now(UTC) - timedelta(days=min(max(days, 1), 365))
    rows = (
        await session.execute(
            select(
                LlmCall.purpose,
                LlmCall.model,
                func.count(),
                func.sum(LlmCall.input_tokens),
                func.sum(LlmCall.output_tokens),
                func.sum(LlmCall.cost_estimate_usd),
                func.avg(LlmCall.latency_ms),
                func.count().filter(LlmCall.status != "ok"),
            )
            .where(LlmCall.org_id == ctx.org_id, LlmCall.created_at >= since)
            .group_by(LlmCall.purpose, LlmCall.model)
        )
    ).all()
    by = [
        {
            "purpose": p,
            "model": mdl,
            "calls": n,
            "input_tokens": int(i or 0),
            "output_tokens": int(o or 0),
            "cost_usd": round(float(c or 0), 4),
            "avg_latency_ms": round(float(lat or 0), 1),
            "errors": int(err or 0),
        }
        for p, mdl, n, i, o, c, lat, err in rows
    ]
    return {
        "days": days,
        "calls": sum(x["calls"] for x in by),
        "cost_usd": round(sum(x["cost_usd"] for x in by), 4),
        "by_purpose": by,
    }

"""Admin: AI usage telemetry."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter
from sqlalchemy import func, select

from twinpm.db.models import LlmCall
from twinpm.deps import DB, AdminCtx, Ctx

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


@router.post("/reset-demo", response_model=dict[str, Any])
async def reset_demo(ctx: Ctx, session: DB) -> dict[str, Any]:
    """Re-seed the NovaPay demo org (deterministic). Org admins always; TPMs in demo mode.

    Seeds, then refreshes predictions, forecasts, anomalies, health and themes before returning,
    so no screen sees a half-reset org.
    """
    import time

    from twinpm.config import get_settings
    from twinpm.core.errors import ForbiddenError
    from twinpm.core.rbac import Perm, has_perm
    from twinpm.db.models import Organization
    from twinpm.seed.generator import generate
    from twinpm.seed.loader import load
    from twinpm.services.ml_jobs import refresh_org, refresh_themes

    s = get_settings()
    org = await session.get(Organization, ctx.org_id)
    if org is None or org.slug != "novapay":
        raise ForbiddenError("Reset is only available for the NovaPay demo org")
    if not (has_perm(ctx.role, Perm.ADMIN) or (s.effective_demo_mode and ctx.role == "tpm")):
        raise ForbiddenError("Only org admins can reset the demo")
    t0 = time.perf_counter()
    await session.rollback()
    await load(session, generate(42), s.seed_demo_password.get_secret_value())
    seeded = round(time.perf_counter() - t0, 2)

    await refresh_org(session, ctx.org_id)
    await refresh_themes(session, ctx.org_id)
    total = round(time.perf_counter() - t0, 2)
    return {"status": "reset", "seed_seconds": seeded, "total_seconds": total}

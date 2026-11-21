"""Insights agent entry point for metric questions.

With an LLM configured, the insights graph (Phase 6) plans the `query_metric` call; otherwise
the deterministic parser maps the question onto the same parameterised tool.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from twinpm.core.tenancy import TenantContext
from twinpm.schemas.risk import AskOut
from twinpm.services import insights


async def answer(session: AsyncSession, ctx: TenantContext, question: str) -> AskOut:
    return await insights.ask(session, ctx, question)

"""TwinPM as an MCP server (streamable HTTP at /mcp).

Authenticated with per-user API tokens (`Authorization: Bearer tpm_...`). Tools are the same
functions the agents use, scoped to the token owner's tenant and role. The suggestion-creating
tool goes through the same autonomy policy gate as the twin.
"""

from __future__ import annotations

import json
from contextvars import ContextVar
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.types import ASGIApp, Receive, Scope, Send

from twinpm.agents import tools as t
from twinpm.config import get_settings
from twinpm.core.errors import AppError
from twinpm.core.rbac import Perm, ensure
from twinpm.core.tenancy import TenantContext
from twinpm.db.session import get_sessionmaker

mcp_ctx: ContextVar[TenantContext | None] = ContextVar("mcp_ctx", default=None)

mcp = FastMCP(
    "TwinPM",
    instructions="Read your program's health, briefing, risks, forecast and decisions, and "
    "propose actions that go through your autonomy policy.",
    stateless_http=True,
    json_response=True,
    streamable_http_path="/",
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=get_settings().mcp_allowed_hosts,
    ),
)


async def _run(fn: Any, args: Any) -> str:
    ctx = mcp_ctx.get()
    if ctx is None:
        raise PermissionError("Not authenticated")
    ensure(ctx, Perm.READ)
    async with get_sessionmaker()() as session:
        try:
            out = await fn(session, ctx, args)
            await session.commit()
        except AppError as exc:
            out = {"data": {"error": exc.message}, "citations": []}
    return json.dumps(out, default=str)


@mcp.tool(description="Program health score, sub-scores and drivers.")
async def program_health() -> str:
    return await _run(t.get_health, t.NoArgs())


@mcp.tool(description="Today's morning briefing: the top three attention items.")
async def briefing() -> str:
    async def fn(session: Any, ctx: TenantContext, _: Any) -> dict[str, Any]:
        from twinpm.services import ml_jobs, program

        prog, _ms = await ml_jobs.program_context(session, ctx.org_id)
        b = await program.briefing(session, ctx, prog.id)
        return {"data": b.model_dump(mode="json")}

    return await _run(fn, None)


@mcp.tool(description="Open work items above a delay-risk threshold, with drivers.")
async def risky_items(min_score: float = 0.6) -> str:
    return await _run(t.get_risky_items, t.RiskyArgs(min_score=min_score))


@mcp.tool(description="Latest launch forecast (P50/P80/P95).")
async def forecast() -> str:
    return await _run(t.run_forecast, t.NoArgs())


@mcp.tool(description="Search the decision log.")
async def search_decisions(query: str) -> str:
    return await _run(t.search_decisions, t.Query(query=query))


@mcp.tool(
    description="Propose reassigning work items to a person. Creates a suggestion that "
    "follows your autonomy policy; it does not bypass approval."
)
async def propose_reassignment(work_items: list[str], to_person: str, reason: str = "") -> str:
    async def fn(session: Any, ctx: TenantContext, args: t.ReassignArgs) -> dict[str, Any]:
        from twinpm.services import suggestions

        ensure(ctx, Perm.PROGRAM_WRITE)
        out = await t.propose_reassignment(session, ctx, args)
        a = out["proposed_action"]
        s = await suggestions.create(
            session,
            ctx,
            type=a["type"],
            title=a["title"],
            payload=a["payload"],
            agent="mcp",
            explanation=a.get("explanation", ""),
            citations=out["citations"],
        )
        return {
            "data": {
                "suggestion_id": str(s.id) if s else None,
                "status": s.status if s else "observed",
            },
            "citations": out["citations"],
        }

    return await _run(fn, t.ReassignArgs(work_items=work_items, to_person=to_person, reason=reason))


class TokenAuth:
    """ASGI middleware: resolve the bearer API token to a tenant context for MCP calls."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        from twinpm.deps import API_TOKEN_PREFIX, resolve_api_token

        headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
        auth = headers.get("authorization", "")
        raw = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
        ctx = None
        if raw.startswith(API_TOKEN_PREFIX):
            try:
                async with get_sessionmaker()() as s:
                    user = await resolve_api_token(s, raw)
                    await s.commit()
                ctx = TenantContext(org_id=user.org_id, user_id=user.id, role=user.role)
            except AppError:
                ctx = None
        if ctx is None:
            body = b'{"error":{"code":"unauthorized","message":"Valid API token required"}}'
            await send(
                {
                    "type": "http.response.start",
                    "status": 401,
                    "headers": [(b"content-type", b"application/json")],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return
        token = mcp_ctx.set(ctx)
        try:
            await self.app(scope, receive, send)
        finally:
            mcp_ctx.reset(token)


def mcp_asgi_app() -> ASGIApp:
    return TokenAuth(mcp.streamable_http_app())

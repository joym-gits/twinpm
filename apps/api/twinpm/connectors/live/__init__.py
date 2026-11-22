"""Live connector dispatch (feature-flagged per integration via mode='live')."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from twinpm.connectors.base import SyncResult
from twinpm.core.crypto import decrypt_config
from twinpm.core.errors import AppError
from twinpm.core.tenancy import TenantContext
from twinpm.db import models as m


async def sync_live(session: AsyncSession, ctx: TenantContext, integ: m.Integration) -> SyncResult:
    cfg = decrypt_config(integ.config or {})
    if integ.provider == "jira":
        from twinpm.connectors.jira.client import JiraClient
        from twinpm.connectors.upsert import upsert_work_items

        async with JiraClient(cfg["base_url"], cfg["email"], cfg["api_token"]) as jira:
            items = await jira.list_work_items(integ.last_sync_at, cfg.get("jql", ""))
        return await upsert_work_items(session, ctx, items)
    if integ.provider == "github":
        from twinpm.connectors.github.client import GitHubClient
        from twinpm.connectors.upsert import apply_pull_requests

        async with GitHubClient(cfg["token"], cfg["repo"]) as gh:
            prs = await gh.list_pull_requests(integ.last_sync_at)
        return await apply_pull_requests(session, ctx, prs)
    if integ.provider == "slack":
        return SyncResult("slack", details=["slack is outbound only"])
    raise AppError(f"No live adapter for {integ.provider}")

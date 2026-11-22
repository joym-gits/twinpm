"""MCP: TwinPM's server requires an API token and honours RBAC/policy; the client seam loads
tools from a (mock) vendor MCP server."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from mcp.server.fastmcp import FastMCP

pytestmark = pytest.mark.usefixtures("seeded")


@pytest.fixture(scope="session")
async def mcp_running() -> AsyncIterator[None]:
    """Hold the session manager open in one task (anyio cancel scopes are task-bound)."""
    import asyncio

    from twinpm.agents.mcp_server import mcp

    stop = asyncio.Event()

    async def hold() -> None:
        async with mcp.session_manager.run():
            await stop.wait()

    task = asyncio.create_task(hold())
    await asyncio.sleep(0)
    yield
    stop.set()
    await task


def _factory(app: Any) -> Any:
    def make(
        headers: dict[str, str] | None = None, timeout: Any = None, auth: Any = None
    ) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            headers=headers,
            timeout=timeout,
            auth=auth,
            base_url="http://test",
        )

    return make


async def test_mcp_requires_token(app: Any, mcp_running: None) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        r = await c.post("/mcp/", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert r.status_code == 401


async def test_mcp_tools_with_token(app: Any, priya: httpx.AsyncClient, mcp_running: None) -> None:
    from langchain_mcp_adapters.client import MultiServerMCPClient

    tok = (await priya.post("/api/v1/api-tokens", json={"name": "claude desktop"})).json()
    assert tok["token"].startswith("tpm_")
    client = MultiServerMCPClient(
        {
            "twinpm": {
                "transport": "streamable_http",
                "url": "http://test/mcp/",
                "headers": {"Authorization": f"Bearer {tok['token']}"},
                "httpx_client_factory": _factory(app),
            }
        }
    )
    tools = {t.name: t for t in await client.get_tools()}
    assert {
        "program_health",
        "briefing",
        "risky_items",
        "forecast",
        "search_decisions",
        "propose_reassignment",
    } <= set(tools)
    out = await tools["forecast"].ainvoke({})
    text = out if isinstance(out, str) else json.dumps(out, default=str)
    assert "p80" in text
    prop = await tools["propose_reassignment"].ainvoke(
        {"work_items": ["PAY-250"], "to_person": "Karan Malhotra"}
    )
    ptext = prop if isinstance(prop, str) else json.dumps(prop, default=str)
    assert "pending" in ptext  # L3 by default: a suggestion, not an executed change
    await priya.delete(f"/api/v1/api-tokens/{tok['id']}")
    revoked = MultiServerMCPClient(
        {
            "twinpm": {
                "transport": "streamable_http",
                "url": "http://test/mcp/",
                "headers": {"Authorization": f"Bearer {tok['token']}"},
                "httpx_client_factory": _factory(app),
            }
        }
    )
    with pytest.raises(Exception):  # noqa: B017, PT011 - the transport raises on the 401
        await revoked.get_tools()


async def test_client_seam_loads_vendor_tools() -> None:
    from mcp.server.transport_security import TransportSecuritySettings

    from twinpm.connectors.mcp_client import load_vendor_tools

    vendor = FastMCP(
        "mock-jira",
        stateless_http=True,
        json_response=True,
        streamable_http_path="/",
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )

    @vendor.tool(description="Search issues")
    async def search_issues(jql: str) -> str:
        return json.dumps([{"key": "PAY-1", "summary": f"match for {jql}"}])

    app = vendor.streamable_http_app()
    async with vendor.session_manager.run():
        tools = await load_vendor_tools(
            {
                "jira": {
                    "transport": "streamable_http",
                    "url": "http://test/",
                    "httpx_client_factory": _factory(app),
                }
            }
        )
        assert [t.name for t in tools] == ["jira_search_issues"]
        res = await tools[0].ainvoke({"jql": "project = PAY"})
    assert "PAY-1" in (res if isinstance(res, str) else json.dumps(res, default=str))

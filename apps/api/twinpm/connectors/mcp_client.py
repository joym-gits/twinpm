"""MCP client seam: load vendor MCP servers (Jira, GitHub, Slack...) as LangChain tools.

Configured with MCP_SERVERS (JSON: {"jira": {"transport": "streamable_http", "url": ...}}).
Agents receive these tools alongside TwinPM's own, so a live connector can be swapped for a
vendor MCP server without changing agent code.
"""

from __future__ import annotations

import json
import os
from typing import Any

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient


def configured_servers() -> dict[str, Any]:
    raw = os.environ.get("MCP_SERVERS", "").strip()
    return json.loads(raw) if raw else {}


async def load_vendor_tools(connections: dict[str, Any] | None = None) -> list[BaseTool]:
    conns = connections if connections is not None else configured_servers()
    if not conns:
        return []
    client = MultiServerMCPClient(conns, tool_name_prefix=True)
    return await client.get_tools()

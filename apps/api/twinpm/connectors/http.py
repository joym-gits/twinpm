"""Shared HTTP behaviour for live adapters: retries on 429/5xx honouring Retry-After."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

MAX_RETRIES = 4


async def request(client: httpx.AsyncClient, method: str, url: str, **kw: Any) -> httpx.Response:
    for attempt in range(MAX_RETRIES + 1):
        resp = await client.request(method, url, **kw)
        if resp.status_code == 429 or resp.status_code >= 500:
            if attempt == MAX_RETRIES:
                resp.raise_for_status()
            retry_after = resp.headers.get("retry-after")
            delay = float(retry_after) if retry_after and retry_after.isdigit() else 2**attempt
            await asyncio.sleep(min(delay, 30.0))
            continue
        if resp.status_code == 403 and resp.headers.get("x-ratelimit-remaining") == "0":
            reset = float(resp.headers.get("x-ratelimit-reset", "0"))
            wait = max(0.0, reset - asyncio.get_running_loop().time()) if reset < 1e9 else 1.0
            if attempt == MAX_RETRIES:
                resp.raise_for_status()
            await asyncio.sleep(min(wait, 30.0))
            continue
        resp.raise_for_status()
        return resp
    raise RuntimeError("unreachable")

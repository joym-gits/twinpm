"""Slack Web API adapter: post messages and read channel history (cursor pagination)."""

from __future__ import annotations

from types import TracebackType

import httpx

from twinpm.connectors.base import ChatMessageDTO
from twinpm.connectors.http import request
from twinpm.core.errors import AppError


class SlackClient:
    def __init__(self, bot_token: str, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._client = httpx.AsyncClient(
            base_url="https://slack.com/api",
            timeout=30,
            transport=transport,
            headers={"Authorization": f"Bearer {bot_token}"},
        )

    async def __aenter__(self) -> SlackClient:
        return self

    async def __aexit__(self, *exc: object | TracebackType) -> None:
        await self._client.aclose()

    async def post_message(self, channel: str, text: str) -> str:
        data = (
            await request(
                self._client, "POST", "/chat.postMessage", json={"channel": channel, "text": text}
            )
        ).json()
        if not data.get("ok"):
            raise AppError(f"Slack error: {data.get('error')}")
        return str(data["ts"])

    async def history(self, channel: str, limit: int = 50) -> list[ChatMessageDTO]:
        out: list[ChatMessageDTO] = []
        cursor = None
        while len(out) < limit:
            params = {"channel": channel, "limit": min(200, limit - len(out))}
            if cursor:
                params["cursor"] = cursor
            data = (
                await request(self._client, "GET", "/conversations.history", params=params)
            ).json()
            if not data.get("ok"):
                raise AppError(f"Slack error: {data.get('error')}")
            out += [
                ChatMessageDTO(
                    channel=channel, text=x.get("text", ""), ts=x["ts"], user=x.get("user")
                )
                for x in data.get("messages", [])
            ]
            cursor = (data.get("response_metadata") or {}).get("next_cursor")
            if not cursor:
                break
        return out

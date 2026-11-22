"""GitHub REST adapter: pull requests with first-review time, paginated via the Link header."""

from __future__ import annotations

import re
from datetime import datetime
from types import TracebackType
from typing import Any

import httpx

from twinpm.connectors.base import PullRequestDTO
from twinpm.connectors.http import request

KEY = re.compile(r"\b([A-Z]{2,6}-\d+)\b")
NEXT = re.compile(r'<([^>]+)>;\s*rel="next"')


def _ts(v: str | None) -> datetime | None:
    return datetime.fromisoformat(v.replace("Z", "+00:00")) if v else None


class GitHubClient:
    def __init__(
        self,
        token: str,
        repo: str,
        base_url: str = "https://api.github.com",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.repo = repo
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=30,
            transport=transport,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )

    async def __aenter__(self) -> GitHubClient:
        return self

    async def __aexit__(self, *exc: object | TracebackType) -> None:
        await self._client.aclose()

    async def _paged(self, url: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        next_url: str | None = url
        while next_url:
            resp = await request(self._client, "GET", next_url, params=params)
            out += resp.json()
            m = NEXT.search(resp.headers.get("link", ""))
            next_url, params = (m.group(1), {}) if m else (None, {})
        return out

    async def list_pull_requests(self, since: datetime | None) -> list[PullRequestDTO]:
        prs = await self._paged(
            f"/repos/{self.repo}/pulls",
            {"state": "all", "sort": "updated", "direction": "desc", "per_page": 100},
        )
        out = []
        for pr in prs:
            updated = _ts(pr["updated_at"])
            if since and updated and updated < since:
                break
            reviews = await self._paged(
                f"/repos/{self.repo}/pulls/{pr['number']}/reviews", {"per_page": 100}
            )
            times = [t for t in (_ts(r.get("submitted_at")) for r in reviews) if t]
            first = min(times) if times else None
            key = KEY.search(f"{pr['title']} {pr.get('head', {}).get('ref', '')}")
            out.append(
                PullRequestDTO(
                    external_id=str(pr["id"]),
                    title=pr["title"],
                    work_item_key=key.group(1) if key else None,
                    state="merged" if pr.get("merged_at") else pr["state"],
                    opened_at=_ts(pr["created_at"]) or datetime.min,
                    first_review_at=first,
                    merged_at=_ts(pr.get("merged_at")),
                    author=(pr.get("user") or {}).get("login"),
                )
            )
        return out

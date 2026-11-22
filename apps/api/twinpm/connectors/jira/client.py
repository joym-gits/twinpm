"""Jira Cloud REST v3 adapter (search by JQL, paginated with nextPageToken)."""

from __future__ import annotations

from datetime import datetime
from types import TracebackType
from typing import Any

import httpx

from twinpm.connectors.base import WorkItemDTO
from twinpm.connectors.http import request

STATUS_MAP = {
    "to do": "todo",
    "open": "todo",
    "backlog": "todo",
    "in progress": "in_progress",
    "in review": "in_review",
    "code review": "in_review",
    "blocked": "blocked",
    "done": "done",
    "closed": "done",
    "resolved": "done",
}
TYPE_MAP = {"story": "story", "task": "task", "bug": "bug", "spike": "spike", "sub-task": "task"}
FIELDS = "summary,status,issuetype,assignee,labels,updated,parent,customfield_10016"


class JiraClient:
    def __init__(
        self,
        base_url: str,
        email: str,
        api_token: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            auth=(email, api_token),
            headers={"Accept": "application/json"},
            timeout=30,
            transport=transport,
        )

    async def __aenter__(self) -> JiraClient:
        return self

    async def __aexit__(self, *exc: object | TracebackType) -> None:
        await self._client.aclose()

    @staticmethod
    def _dto(issue: dict[str, Any]) -> WorkItemDTO:
        f = issue["fields"]
        status = STATUS_MAP.get(str(f["status"]["name"]).lower(), "todo")
        return WorkItemDTO(
            external_key=issue["key"],
            title=f["summary"],
            status=status,
            type=TYPE_MAP.get(str(f["issuetype"]["name"]).lower(), "task"),
            story_points=f.get("customfield_10016"),
            assignee_email=(f.get("assignee") or {}).get("emailAddress"),
            epic_key=(f.get("parent") or {}).get("key"),
            updated_at=datetime.fromisoformat(f["updated"].replace("Z", "+00:00")),
            labels=f.get("labels") or [],
            raw={"id": issue["id"]},
        )

    async def list_work_items(self, since: datetime | None, jql: str = "") -> list[WorkItemDTO]:
        clauses = [jql] if jql else []
        if since:
            clauses.append(f'updated >= "{since:%Y-%m-%d %H:%M}"')
        query = " AND ".join(f"({c})" for c in clauses) or "order by updated"
        out: list[WorkItemDTO] = []
        token: str | None = None
        while True:
            params: dict[str, Any] = {"jql": query, "fields": FIELDS, "maxResults": 100}
            if token:
                params["nextPageToken"] = token
            data = (
                await request(self._client, "GET", "/rest/api/3/search/jql", params=params)
            ).json()
            out += [self._dto(i) for i in data.get("issues", [])]
            token = data.get("nextPageToken")
            if not token or data.get("isLast", True):
                break
        return out

"""Live adapters against recorded HTTP fixtures (respx), idempotent upserts, mock ticks and
worker jobs."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
import respx
from sqlalchemy import func, select

from twinpm.connectors.github.client import GitHubClient
from twinpm.connectors.jira.client import JiraClient
from twinpm.connectors.slack.client import SlackClient
from twinpm.tests.fixtures import http as fx


@respx.mock
async def test_jira_paginates_and_retries_on_429() -> None:
    route = respx.get("https://novapay.atlassian.net/rest/api/3/search/jql")
    route.side_effect = [
        httpx.Response(429, headers={"retry-after": "0"}),
        httpx.Response(200, json=fx.JIRA_PAGE_1),
        httpx.Response(200, json=fx.JIRA_PAGE_2),
    ]
    async with JiraClient("https://novapay.atlassian.net", "a@b.c", "tok") as jira:
        items = await jira.list_work_items(datetime(2026, 11, 1, tzinfo=UTC), "project = PAY")
    assert [i.external_key for i in items] == ["PAY-900", "PAY-901"]
    assert items[0].status == "in_progress" and items[1].status == "done"
    assert items[0].story_points == 3 and items[0].epic_key == "PAY-E1"
    assert route.call_count == 3
    sent = route.calls[1].request.url.params
    assert "updated >=" in sent["jql"] and "project = PAY" in sent["jql"]
    assert route.calls[2].request.url.params["nextPageToken"] == "tok2"


@respx.mock
async def test_github_link_pagination_and_review_latency() -> None:
    base = "https://api.github.com/repos/novapay/checkout"
    respx.get(f"{base}/pulls").mock(
        side_effect=[
            httpx.Response(
                200, json=fx.GITHUB_PULLS, headers={"link": f'<{base}/pulls?page=2>; rel="next"'}
            ),
            httpx.Response(200, json=fx.GITHUB_PULLS_2),
        ]
    )
    respx.get(f"{base}/pulls/42/reviews").mock(
        return_value=httpx.Response(200, json=fx.GITHUB_REVIEWS)
    )
    respx.get(f"{base}/pulls/43/reviews").mock(return_value=httpx.Response(200, json=[]))
    async with GitHubClient("ghp_x", "novapay/checkout") as gh:
        prs = await gh.list_pull_requests(None)
    assert [p.work_item_key for p in prs] == ["PAY-900", None]
    assert prs[0].first_review_at == datetime(2026, 11, 20, 3, tzinfo=UTC)
    assert prs[1].state == "merged"


@respx.mock
async def test_slack_post_and_cursor_history() -> None:
    respx.post("https://slack.com/api/chat.postMessage").mock(
        return_value=httpx.Response(200, json=fx.SLACK_POST)
    )
    respx.get("https://slack.com/api/conversations.history").mock(
        side_effect=[
            httpx.Response(200, json=fx.SLACK_HISTORY_1),
            httpx.Response(200, json=fx.SLACK_HISTORY_2),
        ]
    )
    async with SlackClient("xoxb-test") as slack:
        assert await slack.post_message("C1", "hi") == "1732190000.000100"
        msgs = await slack.history("C1", 10)
    assert [x.text for x in msgs] == ["hello", "world"]


@pytest.mark.usefixtures("seeded")
async def test_upserts_are_idempotent(seeded: dict[str, Any]) -> None:
    from twinpm.connectors.base import PullRequestDTO, WorkItemDTO
    from twinpm.connectors.upsert import apply_pull_requests, upsert_work_items
    from twinpm.core.tenancy import TenantContext
    from twinpm.db import models as m
    from twinpm.db.session import get_sessionmaker

    ctx = TenantContext.system(seeded["org_id"])
    dto = WorkItemDTO(
        "PAY-950",
        "Live item",
        "in_progress",
        "story",
        2.0,
        "vikram@novapay.example",
        None,
        datetime.now(UTC),
    )
    pr = PullRequestDTO(
        "9001",
        "PAY-950 change",
        "PAY-950",
        "open",
        datetime(2026, 11, 20, tzinfo=UTC),
        datetime(2026, 11, 20, 6, tzinfo=UTC),
        None,
        "x",
    )
    async with get_sessionmaker()() as s:
        first = await upsert_work_items(s, ctx, [dto])
        await s.flush()
        second = await upsert_work_items(s, ctx, [dto])
        await s.flush()
        p1 = await apply_pull_requests(s, ctx, [pr])
        p2 = await apply_pull_requests(s, ctx, [pr])
        n = await s.scalar(
            select(func.count())
            .select_from(m.WorkItem)
            .where(m.WorkItem.org_id == ctx.org_id, m.WorkItem.key == "PAY-950")
        )
        item = (
            await s.execute(
                select(m.WorkItem).where(
                    m.WorkItem.key == "PAY-950", m.WorkItem.org_id == ctx.org_id
                )
            )
        ).scalar_one()
        review_hours = item.pr_review_hours
        await s.rollback()
    assert (first.created, second.created, second.updated) == (1, 0, 1)
    assert n == 1
    assert (p1.updated, p2.updated) == (1, 0)
    assert review_hours == 6.0


@pytest.mark.usefixtures("seeded")
async def test_mock_ticks_and_worker_jobs(seeded: dict[str, Any]) -> None:
    from twinpm.connectors.mock.tracker import tick
    from twinpm.db.session import get_sessionmaker
    from twinpm.workers import jobs

    async with get_sessionmaker()() as s:
        res = await tick(s, seeded["org_id"], "jira", n=3, seed=1)
        await s.rollback()
    assert res.events == 3 and res.details
    assert await jobs.heartbeat({})
    sync = await jobs.connector_sync({})
    assert sync["orgs"] >= 1 and sync["events"] > 0
    assert await jobs.morning_briefing({}, force=True) >= 1
    hourly = await jobs.hourly_review({})
    assert str(seeded["org_id"]) in hourly
    assert jobs.briefing_due("UTC", datetime(2026, 11, 22, 7, 31, tzinfo=UTC))
    assert not jobs.briefing_due("Asia/Kolkata", datetime(2026, 11, 22, 7, 31, tzinfo=UTC))


@pytest.mark.usefixtures("seeded")
async def test_integration_endpoints_encrypt_secrets(priya: httpx.AsyncClient) -> None:
    from twinpm.db import models as m
    from twinpm.db.session import get_sessionmaker

    rows = (await priya.get("/api/v1/integrations")).json()
    jira = next(r for r in rows if r["provider"] == "jira")
    r = await priya.patch(
        f"/api/v1/integrations/{jira['id']}",
        json={
            "config": {
                "base_url": "https://x.atlassian.net",
                "email": "a@b.c",
                "api_token": "s3cret",
            }
        },
    )
    assert r.status_code == 200 and r.json()["configured"] and r.json()["mode"] == "mock"
    async with get_sessionmaker()() as s:
        row = await s.get(m.Integration, jira["id"])
        assert row is not None
        assert "s3cret" not in str(row.config) and "enc" in row.config["api_token"]
    sync = (await priya.post(f"/api/v1/integrations/{jira['id']}/sync")).json()
    assert sync["provider"] == "jira"

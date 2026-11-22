"""Recorded HTTP responses (trimmed) from Jira Cloud, GitHub and Slack for adapter tests."""

JIRA_PAGE_1 = {
    "issues": [
        {
            "id": "10001",
            "key": "PAY-900",
            "fields": {
                "summary": "Webhook retries for refunds",
                "status": {"name": "In Progress"},
                "issuetype": {"name": "Story"},
                "assignee": {"emailAddress": "vikram@novapay.example"},
                "labels": ["payments-api"],
                "updated": "2026-11-20T10:00:00.000+0000",
                "parent": {"key": "PAY-E1"},
                "customfield_10016": 3,
            },
        }
    ],
    "nextPageToken": "tok2",
    "isLast": False,
}
JIRA_PAGE_2 = {
    "issues": [
        {
            "id": "10002",
            "key": "PAY-901",
            "fields": {
                "summary": "Idempotency sweeper",
                "status": {"name": "Done"},
                "issuetype": {"name": "Task"},
                "assignee": None,
                "labels": [],
                "updated": "2026-11-21T08:30:00.000+0000",
                "customfield_10016": None,
            },
        }
    ],
    "isLast": True,
}
GITHUB_PULLS = [
    {
        "id": 501,
        "number": 42,
        "title": "PAY-900: retry webhooks",
        "head": {"ref": "feature/PAY-900"},
        "state": "open",
        "created_at": "2026-11-19T09:00:00Z",
        "updated_at": "2026-11-21T09:00:00Z",
        "merged_at": None,
        "user": {"login": "vrao"},
    }
]
GITHUB_PULLS_2 = [
    {
        "id": 502,
        "number": 43,
        "title": "chore: deps",
        "head": {"ref": "deps"},
        "state": "closed",
        "created_at": "2026-11-18T09:00:00Z",
        "updated_at": "2026-11-20T09:00:00Z",
        "merged_at": "2026-11-20T09:00:00Z",
        "user": {"login": "bot"},
    }
]
GITHUB_REVIEWS = [{"id": 9, "state": "APPROVED", "submitted_at": "2026-11-20T03:00:00Z"}]
SLACK_POST = {"ok": True, "channel": "C1", "ts": "1732190000.000100"}
SLACK_HISTORY_1 = {
    "ok": True,
    "messages": [{"text": "hello", "ts": "1.1", "user": "U1"}],
    "response_metadata": {"next_cursor": "c2"},
}
SLACK_HISTORY_2 = {
    "ok": True,
    "messages": [{"text": "world", "ts": "1.2", "user": "U2"}],
    "response_metadata": {"next_cursor": ""},
}

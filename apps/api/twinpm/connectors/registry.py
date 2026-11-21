"""Resolve the connector for an org and provider (mock unless the integration is live)."""

from __future__ import annotations

import uuid

from twinpm.connectors.mock.slack import MockSlack


def chat_connector(org_id: uuid.UUID) -> MockSlack:
    # ponytail: always the mock in-request; live Slack posting is routed via the worker sync
    # once an org flips the integration to live (Phase 8 adds the live adapter).
    return MockSlack(org_id)

"""Agent evals in demo mode (CI gate): tool selection, citations, zero policy violations."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.usefixtures("seeded")


async def test_agent_evals() -> None:
    from twinpm.agents.evals.run import run_all

    report = await run_all()
    assert report["policy_violations"] == 0, report["failures"]
    assert report["tool_selection_accuracy"] >= 0.9, report["failures"]
    assert report["citation_validity_rate"] >= 0.95
    assert report["pass_rate"] >= 0.9, [
        (f["id"], {k: v for k, v in f["checks"].items() if not v}) for f in report["failures"]
    ]

"""Agent evals: tool-selection accuracy, citation validity and policy violations.

`python -m twinpm.agents.evals.run [--fail-under 0.9]` runs every scenario against the
configured database (seeded demo org) with DemoChatModel, or Claude when a key is set.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from typing import Any

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy import select

from twinpm.agents.evals.scenarios import SCENARIOS, Scenario
from twinpm.agents.graphs.supervisor import build_supervisor, run_config
from twinpm.agents.guardrails import validate_citations
from twinpm.core.tenancy import TenantContext
from twinpm.db import models as m
from twinpm.db.session import get_sessionmaker
from twinpm.services import policy


async def run_scenario(graph: Any, ctx: TenantContext, name: str, sc: Scenario) -> dict[str, Any]:
    tid = f"{ctx.org_id}:{uuid.uuid4()}"
    cfg = run_config(
        ctx, thread_id=tid, conversation_id=None, program_id=None, user_name=name, persona=None
    )
    out = await graph.ainvoke(
        {"messages": [HumanMessage(content=sc["question"])], "question": sc["question"]}, cfg
    )
    trace = out.get("agent_trace", [])
    agents = [t["agent"] for t in trace if t["event"] == "agent_started"]
    tools = {t["tool"] for t in trace if t["event"] == "tool_call"}
    answer = out.get("answer", "")
    async with get_sessionmaker()() as s:
        valid, dropped = await validate_citations(s, ctx.org_id, out.get("citations", []))
        created = (
            (await s.execute(select(m.Suggestion).where(m.Suggestion.thread_id == tid)))
            .scalars()
            .all()
        )
        violations = []
        for sug in created:
            level = await policy.level_for(s, ctx.org_id, ctx.user_id, sug.type)
            if sug.status == "auto_executed" and level < policy.Level.AUTONOMOUS:
                violations.append(f"{sug.type} executed at L{int(level)}")
            if sug.status != "pending" and sug.status != "auto_executed":
                violations.append(f"{sug.type} resolved without a human ({sug.status})")
    checks = {
        "agents": agents[: len(sc.get("agents", []))] == sc.get("agents", agents),
        "tools": set(sc.get("tools", [])) <= tools,
        "citations": set(sc.get("citation_types", [])) <= {c["type"] for c in valid},
        "approval": bool(out.get("pending_approval")) == sc.get("expect_approval", False),
        "mentions": all(w.lower() in answer.lower() for w in sc.get("must_mention", [])),
        "forbidden": not any(w in answer for w in sc.get("must_not_mention", [])),
    }
    return {
        "id": sc["id"],
        "passed": all(checks.values()),
        "checks": checks,
        "agents": agents,
        "tools": sorted(tools),
        "valid_citations": len(valid),
        "dropped_citations": len(dropped),
        "policy_violations": violations,
    }


async def run_all(slug: str = "novapay") -> dict[str, Any]:
    async with get_sessionmaker()() as s:
        user = (
            (
                await s.execute(
                    select(m.User)
                    .join(m.Organization, m.Organization.id == m.User.org_id)
                    .where(m.Organization.slug == slug, m.User.role == "tpm")
                    .order_by(m.User.name.desc())
                )
            )
            .scalars()
            .first()
        )
    if user is None:
        raise SystemExit("Seed the demo org first: make seed && make train")
    ctx = TenantContext(org_id=user.org_id, user_id=user.id, role=user.role)
    graph = build_supervisor(InMemorySaver())
    results = [await run_scenario(graph, ctx, user.name, sc) for sc in SCENARIOS]
    tool_acc = sum(r["checks"]["tools"] for r in results) / len(results)
    total_cites = sum(r["valid_citations"] + r["dropped_citations"] for r in results)
    validity = (sum(r["valid_citations"] for r in results) / total_cites) if total_cites else 1.0
    return {
        "scenarios": len(results),
        "passed": sum(r["passed"] for r in results),
        "pass_rate": round(sum(r["passed"] for r in results) / len(results), 3),
        "tool_selection_accuracy": round(tool_acc, 3),
        "citation_validity_rate": round(validity, 3),
        "policy_violations": sum(len(r["policy_violations"]) for r in results),
        "failures": [r for r in results if not r["passed"]],
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--fail-under", type=float, default=0.9)
    args = p.parse_args()
    report = asyncio.run(run_all())
    print(json.dumps(report, indent=2, default=str))
    if report["policy_violations"] or report["tool_selection_accuracy"] < args.fail_under:
        sys.exit(1)


if __name__ == "__main__":
    main()

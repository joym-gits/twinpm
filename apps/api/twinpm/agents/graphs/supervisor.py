"""Supervisor graph: the twin's orchestrator.

load_context -> supervisor -> run_specialist (loop over the plan) -> policy_gate
  -> compose_answer -> validate_citations -> finalize
  -> [await_approval (interrupt, L3 actions) -> confirm] -> END

The policy gate is plain Python (services.policy); the LLM never decides permissions.
"""

from __future__ import annotations

import asyncio
import json
import operator
import uuid
from typing import Annotated, Any, Literal, TypedDict

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    RemoveMessage,
    SystemMessage,
)
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import RetryPolicy, interrupt
from pydantic import BaseModel, Field
from sqlalchemy import select

from twinpm.agents import demo_rules
from twinpm.agents.graphs.specialist import harvest, specialist
from twinpm.agents.guardrails import Redactor, clean_answer
from twinpm.agents.prompts import persona_block, prompt, prompt_version
from twinpm.agents.tools import ctx_from
from twinpm.core.logging import get_logger
from twinpm.db import models as m
from twinpm.db.session import get_sessionmaker
from twinpm.llm.provider import get_chat_model, is_demo
from twinpm.services import events, suggestions

log = get_logger(__name__)
SPECIALIST_TIMEOUT = 90.0
HISTORY_BUDGET = 16  # messages kept verbatim before older turns are summarised


def merge_dict(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    return {**a, **b}


class TwinState(TypedDict, total=False):
    messages: Annotated[list[BaseMessage], add_messages]
    question: str
    page_context: dict[str, Any]
    plan: list[str]
    step: int
    findings: Annotated[dict[str, str], merge_dict]
    agent_trace: Annotated[list[dict[str, Any]], operator.add]
    citations: Annotated[list[dict[str, Any]], operator.add]
    proposed_actions: Annotated[list[dict[str, Any]], operator.add]
    suggestion_ids: list[str]
    executed: list[dict[str, Any]]
    pending_approval: dict[str, Any] | None
    approval_result: dict[str, Any] | None
    answer: str
    warnings: list[str]


class Plan(BaseModel):
    agents: list[Literal["strategy", "planner", "delegation", "risk", "comms", "insights"]] = Field(
        min_length=1, max_length=4
    )
    reason: str


def _cfg(config: RunnableConfig) -> dict[str, Any]:
    return config.get("configurable") or {}


async def load_context(state: TwinState, config: RunnableConfig) -> dict[str, Any]:
    msgs = state.get("messages", [])
    out: dict[str, Any] = {
        "plan": [],
        "step": 0,
        "findings": {},
        "suggestion_ids": [],
        "executed": [],
        "pending_approval": None,
        "approval_result": None,
        "warnings": [],
        "answer": "",
    }
    if len(msgs) > HISTORY_BUDGET:
        old = msgs[:-8]
        asked = [m.content for m in old if isinstance(m, HumanMessage)][-6:]
        summary = SystemMessage(
            content="Earlier in this conversation the TPM asked: "
            + " | ".join(str(a)[:120] for a in asked),
            id=str(uuid.uuid4()),
        )
        out["messages"] = [RemoveMessage(id=m.id) for m in old if m.id] + [summary]
    return out


async def supervisor(state: TwinState, config: RunnableConfig) -> dict[str, Any]:
    q = state["question"]
    ctx = ctx_from(config)
    if is_demo():
        plan = demo_rules.route(q)
        reason = "intent rules"
    else:
        model = get_chat_model("supervisor", ctx, prompt_version=prompt_version("supervisor"))
        page = state.get("page_context") or {}
        res = await model.with_structured_output(Plan, method="json_schema").ainvoke(
            [
                SystemMessage(content=prompt("supervisor")),
                HumanMessage(content=f"Request: {q}\nCurrent page: {json.dumps(page)}"),
            ],
            config,
        )
        parsed = res if isinstance(res, Plan) else Plan.model_validate(res)
        plan, reason = list(dict.fromkeys(parsed.agents)), parsed.reason
    return {
        "plan": plan,
        "step": 0,
        "agent_trace": [{"agent": "supervisor", "event": "plan", "plan": plan, "reason": reason}],
    }


def route_next(state: TwinState) -> str:
    return "run_specialist" if state.get("step", 0) < len(state.get("plan", [])) else "policy_gate"


async def run_specialist(state: TwinState, config: RunnableConfig) -> dict[str, Any]:
    agent = state["plan"][state["step"]]
    prior = "\n".join(f"{a} found: {t}" for a, t in state.get("findings", {}).items())
    page = state.get("page_context") or {}
    content = state["question"]
    if prior:
        content += f"\n\nWhat other specialists found so far:\n{prior}"
    if page:
        content += f"\n\nThe TPM is looking at: {json.dumps(page)}"
    try:
        out = await asyncio.wait_for(
            specialist(agent).ainvoke({"messages": [HumanMessage(content=content)]}, config),
            timeout=SPECIALIST_TIMEOUT,
        )
        h = harvest(agent, out["messages"])
    except Exception as exc:  # degrade gracefully; keep the partial trace
        log.warning("specialist_failed", agent=agent, error=str(exc))
        h = {
            "text": f"The {agent} specialist could not finish ({type(exc).__name__}).",
            "trace": [{"agent": agent, "event": "error", "error": str(exc)[:200]}],
            "citations": [],
            "actions": [],
        }
    return {
        "step": state["step"] + 1,
        "findings": {agent: h["text"]},
        "agent_trace": h["trace"],
        "citations": h["citations"],
        "proposed_actions": h["actions"],
    }


async def policy_gate(state: TwinState, config: RunnableConfig) -> dict[str, Any]:
    """Route each proposed action through the autonomy policy (deterministic)."""
    ctx = ctx_from(config)
    thread_id = _cfg(config).get("thread_id")
    program_id = _cfg(config).get("program_id")
    created, executed = [], []
    pending: list[dict[str, Any]] = []
    async with get_sessionmaker()() as session:
        for a in state.get("proposed_actions", []):
            s = await suggestions.create(
                session,
                ctx,
                type=a["type"],
                title=a["title"],
                payload=a["payload"],
                agent=a.get("agent", "twin"),
                explanation=a.get("explanation", ""),
                drivers=a.get("drivers"),
                citations=a.get("citations"),
                program_id=uuid.UUID(program_id) if program_id else None,
                thread_id=thread_id,
            )
            if s is None:
                continue
            created.append(str(s.id))
            if s.status == "auto_executed":
                executed.append({"id": str(s.id), "title": s.title})
            elif s.autonomy_level_required >= 3:
                pending.append(
                    {
                        "id": str(s.id),
                        "title": s.title,
                        "type": s.type,
                        "explanation": s.explanation,
                    }
                )
        await session.commit()
    trace = [
        {"agent": "policy_gate", "event": "suggestion_created", "suggestion_id": sid}
        for sid in created
    ]
    approval = (
        {
            "suggestion_ids": [p["id"] for p in pending],
            "items": pending,
            "summary": f"{len(pending)} action(s) need your approval",
        }
        if pending
        else None
    )
    return {
        "suggestion_ids": created,
        "executed": executed,
        "pending_approval": approval,
        "agent_trace": trace,
    }


def after_finalize(state: TwinState) -> str:
    return "await_approval" if state.get("pending_approval") else END


async def await_approval(state: TwinState, config: RunnableConfig) -> dict[str, Any]:
    """L3: pause the graph until the TPM responds. Survives restarts via the checkpointer."""
    decision = interrupt(state["pending_approval"])
    return {
        "approval_result": decision if isinstance(decision, dict) else {"value": decision},
        "agent_trace": [{"agent": "policy_gate", "event": "approval_received"}],
    }


async def compose_answer(state: TwinState, config: RunnableConfig) -> dict[str, Any]:
    ctx = ctx_from(config)
    cfg = _cfg(config)
    name = cfg.get("user_name", "there")
    statuses: dict[str, str] = {}
    if state.get("suggestion_ids"):
        async with get_sessionmaker()() as session:
            rows = (
                await session.execute(
                    select(m.Suggestion.id, m.Suggestion.status).where(
                        m.Suggestion.id.in_([uuid.UUID(x) for x in state["suggestion_ids"]])
                    )
                )
            ).all()
            statuses = {str(i): s for i, s in rows}
    pending = [sid for sid, st in statuses.items() if st == "pending"]
    model = get_chat_model(
        "compose_answer", ctx, agent="compose", prompt_version=prompt_version("compose")
    )
    findings = state.get("findings", {})
    if is_demo():
        payload = {
            "question": state["question"],
            "first_name": name.split()[0],
            "findings": findings,
            "actions": pending,
        }
        msgs: list[BaseMessage] = [HumanMessage(content=json.dumps(payload))]
    else:
        red = Redactor()
        body = "\n\n".join(f"## {a}\n{red.redact(t)}" for a, t in findings.items())
        approvals = "; ".join(f"{sid}: {st}" for sid, st in statuses.items()) or "none"
        msgs = [
            SystemMessage(content=prompt("compose") + "\n\n" + cfg.get("persona_block", "")),
            HumanMessage(
                content=f"TPM request: {state['question']}\n\nSpecialist findings:"
                f"\n{body}\n\nProposed actions and status: {approvals}"
            ),
        ]
    res = await model.ainvoke(msgs, config)
    text = (
        res.content
        if isinstance(res.content, str)
        else "".join(c.get("text", "") for c in res.content if isinstance(c, dict))
    )
    return {"answer": text}


async def validate_citations(state: TwinState, config: RunnableConfig) -> dict[str, Any]:
    ctx = ctx_from(config)
    async with get_sessionmaker()() as session:
        text, valid, warnings = await clean_answer(
            session, ctx.org_id, state.get("answer", ""), state.get("citations", [])
        )
    # Replace the accumulated list with the validated one (reducer appends, so send a marker).
    return {
        "answer": text,
        "warnings": warnings,
        "agent_trace": [
            {
                "agent": "guardrails",
                "event": "citations_validated",
                "valid": len(valid),
                "dropped": len({(c["type"], c["id"]) for c in state.get("citations", [])})
                - len(valid),
            }
        ],
        "messages": [
            AIMessage(content=text, id=str(uuid.uuid4()), additional_kwargs={"citations": valid})
        ],
    }


async def finalize(state: TwinState, config: RunnableConfig) -> dict[str, Any]:
    ctx = ctx_from(config)
    conv_id = _cfg(config).get("conversation_id")
    last = state["messages"][-1]
    cites = last.additional_kwargs.get("citations", []) if isinstance(last, AIMessage) else []
    if conv_id:
        async with get_sessionmaker()() as session:
            session.add(
                m.Message(
                    org_id=ctx.org_id,
                    conversation_id=uuid.UUID(conv_id),
                    role="assistant",
                    content=state.get("answer", ""),
                    citations=cites,
                    tool_calls=[
                        t for t in state.get("agent_trace", []) if t["event"] == "tool_call"
                    ],
                    agent_trace=state.get("agent_trace", []),
                )
            )
            await session.commit()
        await events.publish(ctx.org_id, "chat.message", {"conversation_id": conv_id})
    return {}


async def confirm(state: TwinState, config: RunnableConfig) -> dict[str, Any]:
    """After the TPM responds, post what was executed, rejected or still waiting."""
    ctx = ctx_from(config)
    ids = [uuid.UUID(x) for x in (state.get("pending_approval") or {}).get("suggestion_ids", [])]
    async with get_sessionmaker()() as session:
        rows = (
            await session.execute(
                select(m.Suggestion.title, m.Suggestion.status).where(m.Suggestion.id.in_(ids))
            )
        ).all()
        done = [t for t, st in rows if st in ("accepted", "edited")]
        rejected = [t for t, st in rows if st == "rejected"]
        lines = []
        if done:
            lines.append("Done. Executed and logged: " + "; ".join(done) + ".")
        if rejected:
            lines.append("Skipped at your request: " + "; ".join(rejected) + ".")
        text = " ".join(lines) or "Nothing was executed."
        if done:
            text += " The forecast refreshes on the next run; the audit log has every change."
        conv_id = _cfg(config).get("conversation_id")
        if conv_id:
            session.add(
                m.Message(
                    org_id=ctx.org_id,
                    conversation_id=uuid.UUID(conv_id),
                    role="assistant",
                    content=text,
                    citations=[],
                    tool_calls=[],
                    agent_trace=[{"agent": "policy_gate", "event": "approval_received"}],
                )
            )
        await session.commit()
    if _cfg(config).get("conversation_id"):
        await events.publish(
            ctx.org_id, "chat.message", {"conversation_id": _cfg(config).get("conversation_id")}
        )
    return {
        "pending_approval": None,
        "answer": text,
        "messages": [AIMessage(content=text, id=str(uuid.uuid4()))],
    }


def build_supervisor(checkpointer: Any = None) -> Any:
    llm_retry = RetryPolicy(max_attempts=3, initial_interval=1.0)
    g: StateGraph[TwinState] = StateGraph(TwinState)
    g.add_node("load_context", load_context)
    g.add_node("supervisor", supervisor, retry_policy=llm_retry)
    g.add_node("run_specialist", run_specialist)
    g.add_node("policy_gate", policy_gate)
    g.add_node("await_approval", await_approval)
    g.add_node("compose_answer", compose_answer, retry_policy=llm_retry)
    g.add_node("validate_citations", validate_citations)
    g.add_node("finalize", finalize)
    g.add_edge(START, "load_context")
    g.add_edge("load_context", "supervisor")
    g.add_conditional_edges("supervisor", route_next, ["run_specialist", "policy_gate"])
    g.add_conditional_edges("run_specialist", route_next, ["run_specialist", "policy_gate"])
    g.add_node("confirm", confirm)
    g.add_edge("policy_gate", "compose_answer")
    g.add_edge("compose_answer", "validate_citations")
    g.add_edge("validate_citations", "finalize")
    g.add_conditional_edges("finalize", after_finalize, ["await_approval", END])
    g.add_edge("await_approval", "confirm")
    g.add_edge("confirm", END)
    return g.compile(checkpointer=checkpointer, name="twin_supervisor")


def run_config(
    ctx: Any,
    *,
    thread_id: str,
    conversation_id: str | None,
    program_id: str | None,
    user_name: str,
    persona: Any,
) -> RunnableConfig:
    return {
        "configurable": {
            "thread_id": thread_id,
            "ctx": ctx,
            "conversation_id": conversation_id,
            "program_id": program_id,
            "user_name": user_name,
            "persona_block": persona_block(user_name, persona),
        },
        "recursion_limit": 40,
    }

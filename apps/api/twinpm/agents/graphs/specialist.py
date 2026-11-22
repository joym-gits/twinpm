"""Specialist agents: a ReAct subgraph (model node + tool node) per specialist."""

from __future__ import annotations

import json
from typing import Annotated, Any, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

from twinpm.agents.prompts import prompt, prompt_version
from twinpm.agents.tools import ctx_from, tools_for
from twinpm.llm.provider import get_chat_model

MAX_STEPS = 6


class SpecialistState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


def build_specialist(agent: str) -> Any:
    tools = tools_for(agent)

    async def call_model(state: SpecialistState, config: RunnableConfig) -> dict[str, Any]:
        ctx = ctx_from(config)
        persona = (config.get("configurable") or {}).get("persona_block", "")
        steps = sum(isinstance(m, AIMessage) for m in state["messages"])
        model = get_chat_model(
            f"agent.{agent}", ctx, agent=agent, prompt_version=prompt_version(agent)
        )
        if steps < MAX_STEPS:
            model = model.bind_tools(tools)  # type: ignore[assignment]
        system = SystemMessage(content=f"{prompt(agent)}\n\n{persona}")
        response = await model.ainvoke([system, *state["messages"]], config)
        return {"messages": [response]}

    g: StateGraph[SpecialistState] = StateGraph(SpecialistState)
    g.add_node("agent", call_model)
    g.add_node("tools", ToolNode(tools, handle_tool_errors=True))
    g.add_edge(START, "agent")
    g.add_conditional_edges("agent", tools_condition, {"tools": "tools", END: END})
    g.add_edge("tools", "agent")
    return g.compile(name=agent)


def harvest(agent: str, messages: list[BaseMessage]) -> dict[str, Any]:
    """Pull the answer, trace, citations and proposed actions out of a specialist run."""
    trace: list[dict[str, Any]] = [{"agent": agent, "event": "agent_started"}]
    citations: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []
    for m in messages:
        if isinstance(m, AIMessage):
            for tc in m.tool_calls:
                trace.append(
                    {"agent": agent, "event": "tool_call", "tool": tc["name"], "args": tc["args"]}
                )
        elif isinstance(m, ToolMessage):
            try:
                out = json.loads(m.content if isinstance(m.content, str) else "{}")
            except json.JSONDecodeError:
                out = {}
            citations += out.get("citations", [])
            if out.get("proposed_action"):
                actions.append(out["proposed_action"])
            actions += out.get("proposed_actions", [])
            data = out.get("data")
            summary = (
                f"{len(data)} rows"
                if isinstance(data, list)
                else "error: " + str(data.get("error"))
                if isinstance(data, dict) and data.get("error")
                else "ok"
            )
            trace.append(
                {"agent": agent, "event": "tool_result", "tool": m.name, "summary": summary}
            )
    final = next(
        (m for m in reversed(messages) if isinstance(m, AIMessage) and not m.tool_calls), None
    )
    text = ""
    if final is not None:
        text = (
            final.content
            if isinstance(final.content, str)
            else "".join(c.get("text", "") for c in final.content if isinstance(c, dict))
        )
    trace.append({"agent": agent, "event": "agent_finished"})
    return {"text": text, "trace": trace, "citations": citations, "actions": actions}


_CACHE: dict[str, Any] = {}


def specialist(agent: str) -> Any:
    if agent not in _CACHE:
        _CACHE[agent] = build_specialist(agent)
    return _CACHE[agent]

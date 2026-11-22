# ADR 0002: LangGraph for agent orchestration

Status: accepted. Pinned: `langgraph==1.2.24`, `langchain-core==1.8.4`,
`langchain-anthropic==1.7.12`, `langgraph-checkpoint-postgres==3.2.1`,
`langchain-mcp-adapters==0.3.2`.

## Context
TwinPM's agents plan, call tools, wait for a human approval that may arrive hours later, and
must be inspectable and testable. They run inside our FastAPI app and ARQ worker, against our
own Postgres.

## Decision
Use LangGraph for every multi-step agent workflow, self-hosted (no LangGraph Platform).

- **Human-in-the-loop is built in.** `interrupt()` pauses the supervisor at `await_approval`
  and `Command(resume=...)` continues it. That is TwinPM's L3 "act with approval" level.
- **Durable state.** `AsyncPostgresSaver` stores checkpoints in our Postgres (schema
  `langgraph`), so an approval can arrive after an API restart. A test proves it
  (`test_supervisor_interrupts_and_resumes_after_restart`).
- **Explicit control flow.** A supervisor `StateGraph` routes to specialist subgraphs with
  deterministic edges, per-node retry policies, timeouts and a recursion limit.
- **Streaming.** `astream_events(version="v2")` maps onto our SSE agent-trace events.
- **Model-agnostic.** `ChatAnthropic` in production; `DemoChatModel` (a `BaseChatModel`
  subclass) runs the same graphs offline.
- The policy engine and Action Executor stay plain Python outside the graph; nodes call them.

## Alternatives considered
- **Google ADK**: capable and supports Claude, but fits best with Gemini and Vertex AI Agent
  Engine, which is not our stack.
- **CrewAI**: less control over state, persistence and approvals.
- **Raw Anthropic SDK with our own loop**: more code to build durable state, interrupts and
  streaming ourselves.

## Consequences
- LangGraph APIs move between minor versions; versions are pinned and upgrades need the
  graph tests to pass.
- Current Claude models reject forced `tool_choice` and `temperature`; structured outputs use
  `with_structured_output(method="json_schema")` and effort is set via `output_config`.

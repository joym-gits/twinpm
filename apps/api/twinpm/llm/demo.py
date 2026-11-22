"""DemoChatModel: a deterministic LangChain chat model for offline demo mode.

It makes tool-call decisions from intent rules (`agents.demo_rules.next_tool_calls`) and writes
templated answers from the real tool results (`agents.demo_rules.compose`), so graphs, tools,
policy gates and streaming all run exactly as they do with Claude.
"""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import AsyncIterator, Iterator, Sequence
from typing import Any

from langchain_core.callbacks import AsyncCallbackManagerForLLMRun, CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.tools import BaseTool


def _text(m: BaseMessage) -> str:
    c = m.content
    return (
        c if isinstance(c, str) else " ".join(x.get("text", "") for x in c if isinstance(x, dict))
    )


def _tokens(text: str) -> int:
    return max(1, len(text) // 4)


class DemoChatModel(BaseChatModel):
    agent: str = "general"
    purpose: str = "chat"
    tool_names: list[str] = []

    @property
    def _llm_type(self) -> str:
        return "twinpm-demo"

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> DemoChatModel:
        names = [t.name if isinstance(t, BaseTool) else str(t.get("name")) for t in tools]
        return self.model_copy(update={"tool_names": names})

    def _decide(self, messages: list[BaseMessage]) -> AIMessage:
        from twinpm.agents import demo_rules

        last_human = max(
            (i for i, m in enumerate(messages) if isinstance(m, HumanMessage)), default=-1
        )
        question = _text(messages[last_human]) if last_human >= 0 else ""
        system = " ".join(_text(m) for m in messages if isinstance(m, SystemMessage))
        results: dict[str, list[Any]] = {}
        for m in messages[last_human + 1 :]:
            if isinstance(m, ToolMessage):
                try:
                    payload = json.loads(_text(m))
                except json.JSONDecodeError:
                    payload = {"data": _text(m)}
                results.setdefault(str(m.name), []).append(payload)
        calls = demo_rules.next_tool_calls(self.agent, question, self.tool_names, results)
        prompt_tokens = sum(_tokens(_text(m)) for m in messages)
        if calls:
            msg = AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": n,
                        "args": a,
                        "id": f"call_{uuid.uuid4().hex[:12]}",
                        "type": "tool_call",
                    }
                    for n, a in calls
                ],
            )
            out = 20
        else:
            msg = AIMessage(content=demo_rules.compose(self.agent, question, results, system))
            out = _tokens(_text(msg))
        msg.usage_metadata = {
            "input_tokens": prompt_tokens,
            "output_tokens": out,
            "total_tokens": prompt_tokens + out,
        }
        msg.response_metadata = {"model_name": "demo"}
        return msg

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=self._decide(messages))])

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        return self._generate(messages, stop)

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        msg = self._decide(messages)
        if msg.tool_calls:
            yield ChatGenerationChunk(
                message=AIMessageChunk(
                    content="",
                    tool_call_chunks=[
                        {
                            "name": c["name"],
                            "args": json.dumps(c["args"]),
                            "id": c["id"],
                            "index": i,
                            "type": "tool_call_chunk",
                        }
                        for i, c in enumerate(msg.tool_calls)
                    ],
                    usage_metadata=msg.usage_metadata,
                    response_metadata=msg.response_metadata,
                )
            )
            return
        pieces = re.findall(r"\S+\s*", _text(msg)) or [""]
        for i, tok in enumerate(pieces):
            last = i == len(pieces) - 1
            yield ChatGenerationChunk(
                message=AIMessageChunk(
                    content=tok,
                    usage_metadata=msg.usage_metadata if last else None,
                    response_metadata=msg.response_metadata if last else {},
                )
            )

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        for chunk in self._stream(messages, stop):
            if run_manager and isinstance(chunk.message.content, str) and chunk.message.content:
                await run_manager.on_llm_new_token(chunk.message.content, chunk=chunk)
            yield chunk

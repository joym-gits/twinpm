"""LLM call telemetry: tokens, latency and cost estimate per call, via a LangChain callback."""

from __future__ import annotations

import time
import uuid
from typing import Any

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.outputs import LLMResult

from twinpm.core.logging import get_logger, request_id_var
from twinpm.core.telemetry import LLM_CALLS, LLM_TOKENS

log = get_logger(__name__)
# USD per million tokens (input, output). Anthropic first-party list prices, 2026-11.
PRICES: dict[str, tuple[float, float]] = {
    "claude-opus-5-5": (4.0, 20.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-haiku-5-5": (0.10, 0.50),
    "demo": (0.0, 0.0),
}


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    pin, pout = PRICES.get(model, (0.0, 0.0))
    return round((input_tokens * pin + output_tokens * pout) / 1_000_000, 6)


class LlmCallLogger(AsyncCallbackHandler):
    """Writes one `llm_calls` row per model call. Never fails the call it observes."""

    def __init__(
        self,
        org_id: uuid.UUID,
        user_id: uuid.UUID | None,
        purpose: str,
        prompt_version: str | None = None,
    ) -> None:
        self.org_id, self.user_id = org_id, user_id
        self.purpose, self.prompt_version = purpose, prompt_version
        self._start: dict[uuid.UUID, float] = {}

    async def on_chat_model_start(
        self, serialized: dict[str, Any], messages: Any, *, run_id: uuid.UUID, **kwargs: Any
    ) -> None:
        self._start[run_id] = time.perf_counter()

    async def _record(
        self, run_id: uuid.UUID, model: str, tin: int, tout: int, status: str
    ) -> None:
        from twinpm.db.models import LlmCall
        from twinpm.db.session import get_sessionmaker

        latency = (time.perf_counter() - self._start.pop(run_id, time.perf_counter())) * 1000
        LLM_CALLS.labels(self.purpose, model, status).inc()
        LLM_TOKENS.labels(self.purpose, "input").inc(tin)
        LLM_TOKENS.labels(self.purpose, "output").inc(tout)
        try:
            async with get_sessionmaker()() as s:
                s.add(
                    LlmCall(
                        org_id=self.org_id,
                        user_id=self.user_id,
                        purpose=self.purpose,
                        model=model,
                        input_tokens=tin,
                        output_tokens=tout,
                        latency_ms=round(latency, 1),
                        cost_estimate_usd=cost_usd(model, tin, tout),
                        status=status,
                        prompt_version=self.prompt_version,
                        request_id=request_id_var.get(),
                    )
                )
                await s.commit()
        except Exception as exc:
            log.warning("llm_call_log_failed", error=str(exc))

    async def on_llm_end(self, response: LLMResult, *, run_id: uuid.UUID, **kwargs: Any) -> None:
        tin = tout = 0
        model = "unknown"
        for gens in response.generations:
            for g in gens:
                msg = getattr(g, "message", None)
                usage = getattr(msg, "usage_metadata", None) or {}
                tin += int(usage.get("input_tokens", 0))
                tout += int(usage.get("output_tokens", 0))
                meta = getattr(msg, "response_metadata", None) or {}
                model = str(meta.get("model_name") or meta.get("model") or model)
        await self._record(run_id, model, tin, tout, "ok")

    async def on_llm_error(self, error: BaseException, *, run_id: uuid.UUID, **kwargs: Any) -> None:
        await self._record(run_id, "unknown", 0, 0, "error")

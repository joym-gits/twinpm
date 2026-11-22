"""Chat model factory: ChatAnthropic when a key is configured, DemoChatModel otherwise.

Graphs and endpoints call `get_chat_model(purpose)` and run unchanged in both modes.
"""

from __future__ import annotations

from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel

from twinpm.config import get_settings
from twinpm.core.tenancy import TenantContext
from twinpm.llm.telemetry import LlmCallLogger

ORCHESTRATOR_PURPOSES = {"supervisor", "compose_answer"}


def is_demo() -> bool:
    return get_settings().effective_demo_mode


def get_chat_model(
    purpose: str,
    ctx: TenantContext | None = None,
    agent: str = "general",
    prompt_version: str | None = None,
) -> BaseChatModel:
    callbacks: list[Any] = []
    if ctx is not None:
        callbacks.append(LlmCallLogger(ctx.org_id, ctx.user_id, purpose, prompt_version))
    s = get_settings()
    if s.effective_demo_mode:
        from twinpm.llm.demo import DemoChatModel

        return DemoChatModel(agent=agent, purpose=purpose, callbacks=callbacks)
    from langchain_anthropic import ChatAnthropic

    model = (
        s.anthropic_model_orchestrator if purpose in ORCHESTRATOR_PURPOSES else s.anthropic_model
    )
    key = s.anthropic_api_key.get_secret_value() if s.anthropic_api_key else None
    # No temperature (rejected by current models). Effort is the depth control.
    return ChatAnthropic(
        model=model,
        api_key=key,
        max_tokens=s.llm_max_output_tokens,
        default_request_timeout=s.llm_timeout_seconds,
        max_retries=3,
        callbacks=callbacks,
        output_config={"effort": "medium"},
        stream_usage=True,
    )

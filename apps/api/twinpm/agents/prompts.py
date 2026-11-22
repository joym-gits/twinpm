"""Versioned system prompts (agents/prompts/*.md) and the persona block."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from twinpm.agents.guardrails import INJECTION_NOTICE

PROMPTS_DIR = Path(__file__).parent / "prompts"


@lru_cache
def _load(name: str) -> tuple[str, str]:
    text = (PROMPTS_DIR / f"{name}.md").read_text()
    first, _, body = text.partition("\n")
    version = first.removeprefix("<!-- prompt_version:").removesuffix("-->").strip()
    return version, body.strip()


def prompt(name: str) -> str:
    return f"{_load(name)[1]}\n\n{GROUNDING}\n\n{INJECTION_NOTICE}"


def prompt_version(name: str) -> str:
    return _load(name)[0]


GROUNDING = (
    "Grounding rules: every factual claim must come from a tool result in this conversation. "
    "Name the entities you rely on (work item keys, epic titles, decision titles) so they can "
    "be cited. If the data you need is missing, say so plainly and do not guess. Never claim "
    "an action was taken: proposals go through the autonomy policy and need approval."
)


def persona_block(name: str, persona: Any) -> str:
    if persona is None:
        return f"You are acting as {name}'s twin."
    lines = [f"You are {name}'s twin. Act and write the way {name.split()[0]} would."]
    if persona.priorities:
        lines.append("Priorities, in order: " + "; ".join(persona.priorities[:5]) + ".")
    lines.append(f"Tone: {persona.tone}. Risk tolerance: {persona.risk_tolerance}.")
    for r in (persona.escalation_rules or [])[:3]:
        lines.append(f"Escalation: when {r.get('when')}, {r.get('then')}.")
    if persona.style_examples:
        lines.append("Style examples:\n" + "\n".join(f"- {s}" for s in persona.style_examples[:3]))
    return "\n".join(lines)

"""ReAct-loop Recommendation Agent.

Thin wrapper around the shared AgentLoop engine that binds the PR-recommendation
system prompt and tool set.  All loop logic lives in
``application/use_cases/shared/agent_loop.py``.

Local small-model robustness rules (Qwen2.5 7B via Ollama):
  - Every response is validated against a strict JSON schema before acting on it.
  - On a schema validation failure the error is appended to the conversation and
    the model retries once.
  - Loop cap: 5 iterations max.  If no valid FINAL_ANSWER by then, caller catches
    AgentDidNotConvergeError and falls back to single-shot GenerateRecommendation.
  - Tool results are kept short (≤600 chars each) to preserve context window budget.

Zero infrastructure imports — DB/cache access injected via callable protocols.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.application.use_cases.shared.agent_loop import (
    AgentDidNotConvergeError,
    AgentLoop,
    ToolCallable,
)
from app.domain.interfaces.services import LLMGateway

# Re-export so callers that imported from here keep working.
__all__ = [
    "AgentLoopError",
    "AgentResult",
    "RecommendationAgent",
    "ToolCallable",
    "_parse_json_response",
    "_validate_step",
    "MAX_ITERATIONS",
    "TOOL_NAMES",
]

# Keep the old name as an alias so existing imports don't break.
AgentLoopError = AgentDidNotConvergeError

MAX_ITERATIONS = 5

TOOL_NAMES = {
    "get_story_cluster_context",
    "get_entity_history",
    "get_similar_past_incidents",
    "get_watchlist_status",
}

# ── Expose helpers used by unit tests ────────────────────────────────────────

from app.application.use_cases.shared.agent_loop import (  # noqa: E402
    parse_json_response as _parse_json_response_impl,
    validate_step as _validate_step_impl,
)


def _parse_json_response(raw: str) -> dict[str, Any]:
    return _parse_json_response_impl(raw)


def _validate_step(data: Any) -> dict[str, Any]:
    """Validate a recommendation-agent ReAct step including audience fields."""
    validated = _validate_step_impl(data, TOOL_NAMES)
    if validated.get("type") == "final_answer":
        for aud in ("pr", "exec", "marketing"):
            if aud not in validated:
                raise ValueError(f'final_answer missing required audience "{aud}"')
            rec = validated[aud]
            if not isinstance(rec, dict):
                raise ValueError(f'"{aud}" must be an object')
            if not rec.get("recommendation_text"):
                raise ValueError(f'"{aud}.recommendation_text" must be a non-empty string')
            score = rec.get("confidence_score")
            if not isinstance(score, (int, float)) or not (0.0 <= float(score) <= 1.0):
                raise ValueError(f'"{aud}.confidence_score" must be a float 0.0-1.0')
    return validated


# ── System prompt ─────────────────────────────────────────────────────────────

_SYSTEM = """\
You are a PR intelligence agent generating audience-specific recommendations.
You reason step by step before acting. You may call tools to gather context before
producing your final answer. You must NOT produce prose — every response must be a
single valid JSON object matching one of the two allowed shapes below.

AVAILABLE TOOLS:
  get_story_cluster_context(story_id: str)
    → Full article timeline for this story.
  get_entity_history(entity_id: str, days: int)
    → Recent risk events for this entity over the past N days.
  get_similar_past_incidents(entity_id: str, risk_level: str)
    → Past incidents at the same risk level and whether those recommendations were approved.
  get_watchlist_status(entity_id: str)
    → Whether any user is currently watching this entity (affects alert urgency).

RESPONSE SHAPES — choose exactly one per turn:

Tool call (when you need more context before deciding):
{
  "type": "tool_call",
  "reasoning": "<one sentence: why you need this tool>",
  "tool": "<tool_name>",
  "args": { "<arg>": "<value>" }
}

Final answer (when you have enough context):
{
  "type": "final_answer",
  "reasoning": "<summary of reasoning steps that led to these recommendations>",
  "pr":        { "recommendation_text": "...", "risk_level": "...", "confidence_score": 0.0-1.0, "confidence_rationale": "..." },
  "exec":      { "recommendation_text": "...", "risk_level": "...", "confidence_score": 0.0-1.0, "confidence_rationale": "..." },
  "marketing": { "recommendation_text": "...", "risk_level": "...", "confidence_score": 0.0-1.0, "confidence_rationale": "..." }
}

CONFIDENCE CALIBRATION:
  0.80-1.00: Strong unambiguous signals.
  0.50-0.79: Mixed or evolving situation.
  0.00-0.49: Insufficient evidence — mark needs_human_review.

Never inflate confidence. If you have called all useful tools and still have low
confidence, produce a final_answer with honest low scores rather than more tool calls.
"""


# ── Result dataclass ──────────────────────────────────────────────────────────


@dataclass
class AgentResult:
    pr: dict[str, Any]
    exec_: dict[str, Any]
    marketing: dict[str, Any]
    reasoning: str
    trace: list[dict[str, Any]] = field(default_factory=list)
    iterations_used: int = 0


# ── Agent ─────────────────────────────────────────────────────────────────────


class RecommendationAgent:
    """ReAct loop agent for generating context-aware PR recommendations.

    Parameters
    ----------
    gateway:
        LLMGateway — the local Ollama client (qwen2.5:7b).
    tools:
        Mapping of tool_name → async callable(args_dict) → str result.
        All four tool names from TOOL_NAMES should be present; missing tools
        are handled gracefully (the model is told the tool is unavailable).
    max_tokens_per_step:
        Max tokens per LLM call in the loop.
    """

    def __init__(
        self,
        gateway: LLMGateway,
        tools: dict[str, ToolCallable],
        max_tokens_per_step: int = 600,
    ) -> None:
        self._loop = AgentLoop(
            gateway=gateway,
            system_prompt=_SYSTEM,
            tool_names=TOOL_NAMES,
            tools=tools,
            max_iterations=MAX_ITERATIONS,
            max_tokens_per_step=max_tokens_per_step,
            agent_name="recommendation_agent",
        )

    async def run(
        self,
        story_id: str,
        entity_id: str,
        story_title: str,
        what_happened: str,
        why_happened: str,
        article_count: int,
        recent_headlines: list[str],
        entity_names: list[str],
        risk_level: str = "low",
    ) -> AgentResult:
        """Execute the ReAct loop and return a final AgentResult.

        Raises AgentDidNotConvergeError (aliased as AgentLoopError) if the loop
        exhausts MAX_ITERATIONS — callers should catch this and fall back to
        single-shot.
        """
        headlines_str = "\n".join(f"- {h}" for h in recent_headlines[:8])
        entities_str = ", ".join(entity_names) if entity_names else "unknown"

        initial_context = (
            f"Story ID: {story_id}\n"
            f"Entity ID: {entity_id}\n"
            f"Title: {story_title}\n"
            f"Risk level: {risk_level}\n"
            f"Article count: {article_count}\n"
            f"Entities: {entities_str}\n\n"
            f"What happened:\n{what_happened or '(not yet generated)'}\n\n"
            f"Why it happened:\n{why_happened or '(not yet generated)'}\n\n"
            f"Recent headlines:\n{headlines_str}\n\n"
            f"Reason step by step. Call tools if you need more context, then produce a final_answer."
        )

        result = await self._loop.run(initial_context, run_id=story_id)

        step = result.final_step
        return AgentResult(
            pr=dict(step["pr"]),
            exec_=dict(step["exec"]),
            marketing=dict(step["marketing"]),
            reasoning=result.reasoning,
            trace=result.trace,
            iterations_used=result.iterations_used,
        )

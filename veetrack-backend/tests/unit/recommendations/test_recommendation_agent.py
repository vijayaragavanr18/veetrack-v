"""Unit tests for the RecommendationAgent ReAct loop.

Tests verify:
  - Happy path: model returns final_answer on first iteration.
  - Tool-call path: model calls a tool, observes result, then returns final_answer.
  - Parse-error recovery: invalid JSON → error appended → model retries → final_answer.
  - Loop exhaustion: model keeps calling tools → AgentLoopError after MAX_ITERATIONS.
  - Fallback in GenerateRecommendation: AgentLoopError triggers single-shot path.
  - Hybrid trigger: high-risk → agentic; low-risk recent event → single-shot.

No infrastructure imports. All I/O is via FakeLLMGateway.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.application.use_cases.recommendations.recommendation_agent import (
    MAX_ITERATIONS,
    AgentLoopError,
    RecommendationAgent,
    _parse_json_response,
    _validate_step,
)
from app.application.use_cases.recommendations.generate_recommendation import (
    GenerateRecommendation,
    _should_run_agentic,
)

# ── Helpers ───────────────────────────────────────────────────────────────────

_VALID_FINAL_ANSWER = {
    "type": "final_answer",
    "reasoning": "Sufficient context to act.",
    "pr": {
        "recommendation_text": "Issue a statement immediately.",
        "risk_level": "high",
        "confidence_score": 0.85,
        "confidence_rationale": "Clear signals from 5 articles.",
    },
    "exec": {
        "recommendation_text": "Brief the CEO on emerging risk.",
        "risk_level": "medium",
        "confidence_score": 0.75,
        "confidence_rationale": "Moderate signal, situation evolving.",
    },
    "marketing": {
        "recommendation_text": "Pause scheduled campaigns.",
        "risk_level": "high",
        "confidence_score": 0.80,
        "confidence_rationale": "Brand risk requires campaign hold.",
    },
}

_VALID_TOOL_CALL = {
    "type": "tool_call",
    "reasoning": "Need entity history before deciding.",
    "tool": "get_entity_history",
    "args": {"entity_id": "ent-1", "days": 30},
}


class FakeLLMGateway:
    """Returns responses from a preset queue."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = iter(responses)
        self.model_name = "qwen2.5:7b"

    async def complete(self, prompt: str, **kwargs: Any) -> str:
        return next(self._responses)

    async def complete_json(self, prompt: str, schema: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        raw = next(self._responses)
        return json.loads(raw)


def _agent(responses: list[str], tools: dict | None = None) -> RecommendationAgent:
    return RecommendationAgent(
        gateway=FakeLLMGateway(responses),
        tools=tools or {},
    )


_STORY_KWARGS = dict(
    story_id="story-1",
    entity_id="ent-1",
    story_title="Test Crisis",
    what_happened="Something bad happened.",
    why_happened="Market pressure.",
    article_count=5,
    recent_headlines=["Headline A", "Headline B"],
    entity_names=["AcmeCorp"],
    risk_level="high",
)

# ── _parse_json_response / _validate_step ────────────────────────────────────

def test_parse_valid_final_answer() -> None:
    raw = json.dumps(_VALID_FINAL_ANSWER)
    result = _parse_json_response(raw)
    assert result["type"] == "final_answer"


def test_parse_valid_tool_call() -> None:
    raw = json.dumps(_VALID_TOOL_CALL)
    result = _parse_json_response(raw)
    assert result["type"] == "tool_call"
    assert result["tool"] == "get_entity_history"


def test_parse_strips_markdown_fences() -> None:
    raw = f"```json\n{json.dumps(_VALID_FINAL_ANSWER)}\n```"
    result = _parse_json_response(raw)
    assert result["type"] == "final_answer"


def test_parse_invalid_json_raises() -> None:
    with pytest.raises(ValueError, match="Invalid JSON"):
        _parse_json_response("not json at all")


def test_validate_unknown_tool_raises() -> None:
    bad = {**_VALID_TOOL_CALL, "tool": "delete_everything"}
    with pytest.raises(ValueError, match="Unknown tool"):
        _validate_step(bad)


def test_validate_missing_audience_raises() -> None:
    bad = {k: v for k, v in _VALID_FINAL_ANSWER.items() if k != "exec"}
    with pytest.raises(ValueError, match='"exec"'):
        _validate_step(bad)


def test_validate_bad_confidence_score_raises() -> None:
    bad = {
        **_VALID_FINAL_ANSWER,
        "pr": {**_VALID_FINAL_ANSWER["pr"], "confidence_score": 1.5},
    }
    with pytest.raises(ValueError, match="confidence_score"):
        _validate_step(bad)


# ── Agent happy path ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_agent_returns_final_answer_first_iteration() -> None:
    a = _agent([json.dumps(_VALID_FINAL_ANSWER)])
    result = await a.run(**_STORY_KWARGS)
    assert result.iterations_used == 1
    assert result.pr["recommendation_text"] == "Issue a statement immediately."
    assert result.exec_["confidence_score"] == 0.75
    assert len(result.trace) == 1


# ── Agent tool-call path ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_agent_calls_tool_then_returns_final_answer() -> None:
    tool_fn = AsyncMock(return_value="Entity had 2 incidents in last 30 days.")
    a = _agent(
        [json.dumps(_VALID_TOOL_CALL), json.dumps(_VALID_FINAL_ANSWER)],
        tools={"get_entity_history": tool_fn},
    )
    result = await a.run(**_STORY_KWARGS)
    assert result.iterations_used == 2
    tool_fn.assert_awaited_once_with({"entity_id": "ent-1", "days": 30})
    # Trace: tool_call + observation + final_answer = 3 entries
    trace_types = [e["type"] for e in result.trace]
    assert "tool_call" in trace_types
    assert "observation" in trace_types
    assert "final_answer" in trace_types


@pytest.mark.asyncio
async def test_agent_handles_missing_tool_gracefully() -> None:
    # Tool not in tools dict → observation says "not available"
    a = _agent(
        [json.dumps(_VALID_TOOL_CALL), json.dumps(_VALID_FINAL_ANSWER)],
        tools={},  # no tools registered
    )
    result = await a.run(**_STORY_KWARGS)
    assert result.iterations_used == 2
    obs = next(e for e in result.trace if e["type"] == "observation")
    assert "not available" in obs["content"]["result"]


# ── Parse-error recovery ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_agent_recovers_from_parse_error() -> None:
    a = _agent(["this is not json", json.dumps(_VALID_FINAL_ANSWER)])
    result = await a.run(**_STORY_KWARGS)
    assert result.iterations_used == 2
    error_entries = [e for e in result.trace if e["type"] == "error"]
    assert len(error_entries) == 1


# ── Loop exhaustion ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_agent_raises_on_loop_exhaustion() -> None:
    # Always returns a tool_call — never a final_answer
    responses = [json.dumps(_VALID_TOOL_CALL)] * (MAX_ITERATIONS + 2)
    a = _agent(responses)
    with pytest.raises(AgentLoopError):
        await a.run(**_STORY_KWARGS)


# ── Hybrid trigger ────────────────────────────────────────────────────────────

def test_should_run_agentic_high_risk() -> None:
    assert _should_run_agentic("high", days_since_last_event=5) is True


def test_should_run_agentic_critical_risk() -> None:
    assert _should_run_agentic("critical", days_since_last_event=1) is True


def test_should_run_agentic_first_event() -> None:
    # Low risk but entity hasn't had an event in over 30 days
    assert _should_run_agentic("low", days_since_last_event=None) is True
    assert _should_run_agentic("low", days_since_last_event=45) is True


def test_should_not_run_agentic_routine() -> None:
    # Low risk, recent activity → single-shot path
    assert _should_run_agentic("low", days_since_last_event=3) is False
    assert _should_run_agentic("medium", days_since_last_event=10) is False


# ── GenerateRecommendation fallback ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_generate_recommendation_falls_back_on_agent_loop_error() -> None:
    """When the agent exhausts iterations, GenerateRecommendation falls through to single-shot."""
    # Agent always tool-calls → AgentLoopError → fallback fires single-shot
    agent_responses = [json.dumps(_VALID_TOOL_CALL)] * (MAX_ITERATIONS + 2)
    # Single-shot response (complete_json)
    single_shot_response = json.dumps({
        "pr": {"recommendation_text": "Fallback PR rec.", "risk_level": "low", "confidence_score": 0.7, "confidence_rationale": "Single-shot."},
        "exec": {"recommendation_text": "Fallback exec rec.", "risk_level": "low", "confidence_score": 0.7, "confidence_rationale": "Single-shot."},
        "marketing": {"recommendation_text": "Fallback marketing rec.", "risk_level": "low", "confidence_score": 0.7, "confidence_rationale": "Single-shot."},
    })

    class DualGateway:
        model_name = "qwen2.5:7b"
        _agent_responses = iter(agent_responses)
        _single_shot = json.loads(single_shot_response)

        async def complete(self, prompt: str, **kwargs: Any) -> str:
            return next(self._agent_responses)

        async def complete_json(self, prompt: str, schema: Any, **kwargs: Any) -> dict[str, Any]:
            return self._single_shot

    use_case = GenerateRecommendation(
        gateway=DualGateway(),  # type: ignore[arg-type]
        tools={},
        min_articles=1,
    )
    output = await use_case.run(
        story_id="s1",
        story_title="Test",
        what_happened="x",
        why_happened="y",
        article_count=5,
        recent_headlines=["h"],
        entity_names=["E"],
        entity_id="ent-1",
        risk_level="high",  # triggers agentic path, which will fail
    )
    assert not output.skipped
    assert len(output.results) == 3
    # All came from single-shot fallback
    assert all(r.agent_mode == "single_shot" for r in output.results)
    assert output.results[0].recommendation_text == "Fallback PR rec."

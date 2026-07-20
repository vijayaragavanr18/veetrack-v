"""Unit tests: GenerateRecommendation use case — confidence gating, prompt, edge cases."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.application.use_cases.recommendations.generate_recommendation import (
    DEFAULT_CONFIDENCE_THRESHOLD,
    GenerateRecommendation,
)


def _mock_gateway(response: dict | None = None, error: Exception | None = None) -> AsyncMock:
    gw = AsyncMock()
    gw.model_name = "test-model"
    if error:
        gw.complete_json = AsyncMock(side_effect=error)
    else:
        gw.complete_json = AsyncMock(
            return_value=response
            or {
                "pr": {
                    "recommendation_text": "Issue a press release immediately.",
                    "risk_level": "high",
                    "confidence_score": 0.85,
                    "confidence_rationale": "Clear negative coverage with consistent signals.",
                },
                "exec": {
                    "recommendation_text": "Brief the board before market open.",
                    "risk_level": "medium",
                    "confidence_score": 0.72,
                    "confidence_rationale": "Moderate confidence; situation is evolving.",
                },
                "marketing": {
                    "recommendation_text": "Pause all promotional campaigns.",
                    "risk_level": "high",
                    "confidence_score": 0.45,
                    "confidence_rationale": "Low confidence; unclear impact on brand perception.",
                },
            }
        )
    return gw


def _headlines(n: int = 5) -> list[str]:
    return [f"Headline {i}" for i in range(n)]


# ---------------------------------------------------------------------------
# Happy path — above threshold
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_returns_three_audience_results() -> None:
    gw = _mock_gateway()
    uc = GenerateRecommendation(gateway=gw, confidence_threshold=0.65)
    output = await uc.run("s1", "Apple", "x", "y", 5, _headlines(), ["Apple"])
    assert not output.skipped
    assert len(output.results) == 3
    audiences = {r.audience for r in output.results}
    assert audiences == {"pr", "exec", "marketing"}


@pytest.mark.asyncio
async def test_above_threshold_not_flagged_for_review() -> None:
    gw = _mock_gateway()
    uc = GenerateRecommendation(gateway=gw, confidence_threshold=0.65)
    output = await uc.run("s1", "Apple", "x", "y", 5, _headlines(), [])
    pr = next(r for r in output.results if r.audience == "pr")
    assert not pr.needs_human_review
    assert pr.confidence_score == 0.85


# ---------------------------------------------------------------------------
# Confidence gating — below threshold → needs_human_review
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_below_threshold_flagged_for_review() -> None:
    gw = _mock_gateway()
    uc = GenerateRecommendation(gateway=gw, confidence_threshold=0.65)
    output = await uc.run("s1", "T", "x", "y", 5, _headlines(), [])
    marketing = next(r for r in output.results if r.audience == "marketing")
    assert marketing.confidence_score == 0.45
    assert marketing.needs_human_review


@pytest.mark.asyncio
async def test_at_threshold_not_flagged() -> None:
    """Exactly at threshold → not flagged (boundary is exclusive below)."""
    resp = {
        a: {
            "recommendation_text": "action",
            "risk_level": "low",
            "confidence_score": 0.65,
            "confidence_rationale": "at threshold",
        }
        for a in ("pr", "exec", "marketing")
    }
    gw = _mock_gateway(response=resp)
    uc = GenerateRecommendation(gateway=gw, confidence_threshold=0.65)
    output = await uc.run("s", "T", "x", "y", 5, _headlines(), [])
    assert all(not r.needs_human_review for r in output.results)


@pytest.mark.asyncio
async def test_zero_confidence_always_flagged() -> None:
    resp = {
        a: {
            "recommendation_text": "act",
            "risk_level": "low",
            "confidence_score": 0.0,
            "confidence_rationale": "no evidence",
        }
        for a in ("pr", "exec", "marketing")
    }
    gw = _mock_gateway(response=resp)
    uc = GenerateRecommendation(gateway=gw, confidence_threshold=0.65)
    output = await uc.run("s", "T", "x", "y", 5, _headlines(), [])
    assert all(r.needs_human_review for r in output.results)


# ---------------------------------------------------------------------------
# Too few articles → skip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_skips_when_too_few_articles() -> None:
    gw = _mock_gateway()
    uc = GenerateRecommendation(gateway=gw, min_articles=3)
    output = await uc.run("s", "T", "x", "y", 2, _headlines(), [])
    assert output.skipped
    gw.complete_json.assert_not_called()


@pytest.mark.asyncio
async def test_skips_empty_articles() -> None:
    gw = _mock_gateway()
    uc = GenerateRecommendation(gateway=gw, min_articles=3)
    output = await uc.run("s", "T", "x", "y", 0, [], [])
    assert output.skipped


# ---------------------------------------------------------------------------
# Risk level sanitisation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_risk_level_defaults_to_low() -> None:
    resp = {
        a: {
            "recommendation_text": "act",
            "risk_level": "extreme",  # not in enum
            "confidence_score": 0.8,
            "confidence_rationale": "test",
        }
        for a in ("pr", "exec", "marketing")
    }
    gw = _mock_gateway(response=resp)
    uc = GenerateRecommendation(gateway=gw)
    output = await uc.run("s", "T", "x", "y", 5, _headlines(), [])
    assert all(r.risk_level == "low" for r in output.results)


# ---------------------------------------------------------------------------
# Gateway error propagates
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gateway_error_propagates() -> None:
    gw = _mock_gateway(error=RuntimeError("LLM down"))
    uc = GenerateRecommendation(gateway=gw, min_articles=1)
    with pytest.raises(RuntimeError, match="LLM down"):
        await uc.run("s", "T", "x", "y", 5, _headlines(), [])


# ---------------------------------------------------------------------------
# Confidence threshold is exposed
# ---------------------------------------------------------------------------


def test_confidence_threshold_property() -> None:
    gw = AsyncMock()
    gw.model_name = "m"
    uc = GenerateRecommendation(gateway=gw, confidence_threshold=0.80)
    assert uc.confidence_threshold == 0.80


def test_default_confidence_threshold() -> None:
    gw = AsyncMock()
    gw.model_name = "m"
    uc = GenerateRecommendation(gateway=gw)
    assert uc.confidence_threshold == DEFAULT_CONFIDENCE_THRESHOLD

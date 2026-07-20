"""Unit tests: generate_recommendation task — pure helpers only."""

from __future__ import annotations

import pytest

from workers.tasks.llm.generate_recommendation import RecommendationSettings


def test_settings_default_threshold() -> None:
    s = RecommendationSettings()
    assert 0.0 < s.recommendation_confidence_threshold < 1.0


def test_settings_default_min_articles() -> None:
    s = RecommendationSettings()
    assert s.llm_min_articles >= 3


def test_settings_default_hosted_model() -> None:
    s = RecommendationSettings()
    assert "claude" in s.llm_hosted_model.lower()


def test_settings_empty_api_key_by_default() -> None:
    s = RecommendationSettings()
    # api_key defaults to ""; task uses local tier (vLLM) when no hosted key is set
    assert isinstance(s.anthropic_api_key, str)


def test_settings_threshold_configurable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RECOMMENDATION_CONFIDENCE_THRESHOLD", "0.80")
    s = RecommendationSettings()
    assert s.recommendation_confidence_threshold == pytest.approx(0.80)

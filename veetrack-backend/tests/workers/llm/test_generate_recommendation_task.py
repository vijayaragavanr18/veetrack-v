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


def test_settings_local_model_is_qwen() -> None:
    s = RecommendationSettings()
    assert "qwen" in s.llm_local_model.lower()


def test_settings_local_endpoint_points_to_ollama() -> None:
    s = RecommendationSettings()
    assert "11434" in s.llm_local_endpoint or "localhost" in s.llm_local_endpoint


def test_settings_threshold_configurable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RECOMMENDATION_CONFIDENCE_THRESHOLD", "0.80")
    s = RecommendationSettings()
    assert s.recommendation_confidence_threshold == pytest.approx(0.80)

"""Unit tests: generate_summary task — pure helpers only, no DB/LLM calls."""

from __future__ import annotations

from workers.tasks.llm.generate_summary import MIN_ARTICLES_FOR_SUMMARY, SummarySettings

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def test_min_articles_for_summary_is_positive() -> None:
    assert MIN_ARTICLES_FOR_SUMMARY > 0


# ---------------------------------------------------------------------------
# SummarySettings defaults
# ---------------------------------------------------------------------------


def test_settings_default_local_model_is_qwen() -> None:
    s = SummarySettings()
    assert "qwen" in s.llm_local_model.lower()


def test_settings_default_min_articles() -> None:
    s = SummarySettings()
    assert s.llm_min_articles >= 3


def test_settings_local_endpoint_points_to_vllm() -> None:
    s = SummarySettings()
    assert "8080" in s.llm_local_endpoint or "localhost" in s.llm_local_endpoint

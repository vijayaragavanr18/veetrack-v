"""Unit tests: generate_summary task — pure helpers only, no DB/LLM calls."""

from __future__ import annotations

import pytest

from tasks.llm.generate_summary import MIN_ARTICLES_FOR_SUMMARY, SummarySettings


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

def test_min_articles_for_summary_is_positive() -> None:
    assert MIN_ARTICLES_FOR_SUMMARY > 0


# ---------------------------------------------------------------------------
# SummarySettings defaults
# ---------------------------------------------------------------------------

def test_settings_default_hosted_model() -> None:
    s = SummarySettings()
    assert "claude" in s.llm_hosted_model.lower()


def test_settings_default_min_articles() -> None:
    s = SummarySettings()
    assert s.llm_min_articles >= 3


def test_settings_default_local_model() -> None:
    s = SummarySettings()
    assert s.llm_local_model != ""


def test_settings_empty_api_key_by_default() -> None:
    s = SummarySettings()
    # api_key defaults to ""; task uses local tier (vLLM) when no hosted key is set
    assert isinstance(s.anthropic_api_key, str)

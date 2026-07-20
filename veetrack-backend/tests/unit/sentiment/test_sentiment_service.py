"""Unit tests: ModernBertSentimentService — mocked transformers pipeline."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.domain.interfaces.services import SentimentService
from app.infrastructure.nlp.sentiment_service import (
    ModernBertSentimentService,
    _parse_result,
)

# ---------------------------------------------------------------------------
# _parse_result helper
# ---------------------------------------------------------------------------


def test_parse_positive() -> None:
    r = _parse_result({"label": "positive", "score": 0.92}, False)
    assert r.label == "positive"
    assert r.score == pytest.approx(0.92)
    assert not r.low_confidence


def test_parse_very_positive_maps_to_positive() -> None:
    r = _parse_result({"label": "Very Positive", "score": 0.88}, False)
    assert r.label == "positive"


def test_parse_very_negative_maps_to_negative() -> None:
    r = _parse_result({"label": "very negative", "score": 0.77}, False)
    assert r.label == "negative"


def test_parse_neutral() -> None:
    r = _parse_result({"label": "neutral", "score": 0.61}, False)
    assert r.label == "neutral"


def test_parse_unknown_label_defaults_to_neutral() -> None:
    r = _parse_result({"label": "unclear", "score": 0.5}, False)
    assert r.label == "neutral"


def test_parse_low_confidence_flag_propagated() -> None:
    r = _parse_result({"label": "positive", "score": 0.7}, True)
    assert r.low_confidence is True


# ---------------------------------------------------------------------------
# ModernBertSentimentService protocol conformance
# ---------------------------------------------------------------------------


def test_sentiment_service_satisfies_protocol() -> None:
    assert isinstance(
        ModernBertSentimentService.__new__(ModernBertSentimentService), SentimentService
    )


# ---------------------------------------------------------------------------
# Helper to build a service with a mocked pipeline
# ---------------------------------------------------------------------------


def _make_service(return_value: list[dict]) -> ModernBertSentimentService:
    mock_pipe = MagicMock(return_value=return_value)
    svc = ModernBertSentimentService.__new__(ModernBertSentimentService)
    svc._model_id = "test-model"
    svc._pipe = lambda: mock_pipe  # type: ignore[method-assign]
    return svc


# ---------------------------------------------------------------------------
# analyze — single text
# ---------------------------------------------------------------------------


def test_analyze_positive_text() -> None:
    svc = _make_service([{"label": "positive", "score": 0.95}])
    result = svc.analyze("This is fantastic news for the company!")
    assert result.label == "positive"
    assert result.score == pytest.approx(0.95)
    assert not result.low_confidence


def test_analyze_negative_text() -> None:
    svc = _make_service([{"label": "negative", "score": 0.87}])
    result = svc.analyze("The product launch was a complete disaster.")
    assert result.label == "negative"


def test_analyze_neutral_text() -> None:
    svc = _make_service([{"label": "neutral", "score": 0.72}])
    result = svc.analyze("The company released its quarterly earnings report today.")
    assert result.label == "neutral"


def test_analyze_empty_string_returns_neutral_low_confidence() -> None:
    svc = _make_service([])
    result = svc.analyze("")
    assert result.label == "neutral"
    assert result.low_confidence is True


def test_analyze_whitespace_only_returns_neutral_low_confidence() -> None:
    svc = _make_service([])
    result = svc.analyze("   ")
    assert result.label == "neutral"
    assert result.low_confidence is True


def test_analyze_short_text_flags_low_confidence() -> None:
    svc = _make_service([{"label": "positive", "score": 0.6}])
    result = svc.analyze("Good.")  # 1 word — below threshold
    assert result.low_confidence is True


# ---------------------------------------------------------------------------
# analyze_batch
# ---------------------------------------------------------------------------


def test_analyze_batch_returns_per_text_results() -> None:
    mock_pipe = MagicMock(
        return_value=[
            {"label": "positive", "score": 0.9},
            {"label": "negative", "score": 0.8},
        ]
    )
    svc = ModernBertSentimentService.__new__(ModernBertSentimentService)
    svc._model_id = "test-model"
    svc._pipe = lambda: mock_pipe  # type: ignore[method-assign]

    results = svc.analyze_batch(
        [
            "Great results this quarter!",
            "The layoffs were devastating for morale.",
        ]
    )
    assert len(results) == 2
    assert results[0].label == "positive"
    assert results[1].label == "negative"


def test_analyze_batch_empty_list() -> None:
    svc = _make_service([])
    assert svc.analyze_batch([]) == []


def test_analyze_batch_skips_empty_strings() -> None:
    mock_pipe = MagicMock(return_value=[{"label": "positive", "score": 0.9}])
    svc = ModernBertSentimentService.__new__(ModernBertSentimentService)
    svc._model_id = "test-model"
    svc._pipe = lambda: mock_pipe  # type: ignore[method-assign]

    results = svc.analyze_batch(["", "Excellent results!", ""])
    assert len(results) == 3
    # Empty strings get default neutral/low_confidence
    assert results[0].label == "neutral"
    assert results[0].low_confidence is True
    assert results[2].label == "neutral"
    assert results[2].low_confidence is True
    # Non-empty item gets model result
    assert results[1].label == "positive"

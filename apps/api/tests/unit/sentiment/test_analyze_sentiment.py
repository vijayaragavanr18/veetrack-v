"""Unit tests: AnalyzeSentiment use case — pure logic, no real model."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.application.use_cases.sentiment.analyze_sentiment import AnalyzeSentiment
from app.domain.interfaces.services import SentimentResult


def _stub_service(label: str = "positive", score: float = 0.9) -> MagicMock:
    """Return a mock SentimentService that always returns the given result."""
    result = SentimentResult(label=label, score=score)
    svc = MagicMock()
    svc.analyze.return_value = result
    svc.analyze_batch.return_value = [result]
    return svc


# ---------------------------------------------------------------------------
# run (single article)
# ---------------------------------------------------------------------------

def test_run_positive_content() -> None:
    uc = AnalyzeSentiment(_stub_service("positive", 0.91))
    result = uc.run("Tremendous earnings beat expectations across all segments.")
    assert result.label == "positive"
    assert result.score == pytest.approx(0.91)


def test_run_empty_content_returns_neutral_low_confidence() -> None:
    uc = AnalyzeSentiment(_stub_service())
    result = uc.run("")
    assert result.label == "neutral"
    assert result.low_confidence is True
    # Service should NOT be called for empty content
    uc._service.analyze.assert_not_called()  # type: ignore[attr-defined]


def test_run_whitespace_content_returns_neutral_low_confidence() -> None:
    uc = AnalyzeSentiment(_stub_service())
    result = uc.run("   \n  ")
    assert result.label == "neutral"
    assert result.low_confidence is True


def test_run_service_exception_returns_neutral_low_confidence() -> None:
    svc = MagicMock()
    svc.analyze.side_effect = RuntimeError("model exploded")
    uc = AnalyzeSentiment(svc)
    result = uc.run("Some news content.")
    assert result.label == "neutral"
    assert result.low_confidence is True


# ---------------------------------------------------------------------------
# run_batch
# ---------------------------------------------------------------------------

def test_run_batch_returns_correct_count() -> None:
    svc = MagicMock()
    svc.analyze_batch.return_value = [
        SentimentResult(label="positive", score=0.9),
        SentimentResult(label="negative", score=0.8),
    ]
    uc = AnalyzeSentiment(svc)
    results = uc.run_batch(["Great news.", "Terrible outcome."])
    assert len(results) == 2
    assert results[0].label == "positive"
    assert results[1].label == "negative"


def test_run_batch_empty_list() -> None:
    uc = AnalyzeSentiment(_stub_service())
    assert uc.run_batch([]) == []


def test_run_batch_exception_returns_all_neutral() -> None:
    svc = MagicMock()
    svc.analyze_batch.side_effect = RuntimeError("batch failed")
    uc = AnalyzeSentiment(svc)
    results = uc.run_batch(["a", "b", "c"])
    assert len(results) == 3
    assert all(r.label == "neutral" and r.low_confidence for r in results)

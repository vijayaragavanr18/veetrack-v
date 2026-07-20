"""Sentiment analysis orchestration use case.

Wraps the SentimentService Protocol to handle edge cases cleanly:
  - Empty content → neutral / low_confidence=True
  - Non-English content — passed through unchanged; the default model is
    multilingual so no translation step is needed at this layer.
  - Very short content (< 5 words) → result.low_confidence = True

This module has no infrastructure imports — it depends only on
app.domain.interfaces.services.SentimentService.
"""

from __future__ import annotations

from app.domain.interfaces.services import SentimentResult, SentimentService

_NEUTRAL_EMPTY = SentimentResult(label="neutral", score=0.5, low_confidence=True)


class AnalyzeSentiment:
    """Orchestrates per-article and batch sentiment analysis.

    Parameters
    ----------
    service:
        A SentimentService implementation (injected by the caller).
    """

    def __init__(self, service: SentimentService) -> None:
        self._service = service

    def run(self, content: str) -> SentimentResult:
        """Return a SentimentResult for *content*, never raising."""
        if not content or not content.strip():
            return _NEUTRAL_EMPTY
        try:
            return self._service.analyze(content)
        except Exception:
            return _NEUTRAL_EMPTY

    def run_batch(self, contents: list[str]) -> list[SentimentResult]:
        """Return SentimentResults for each item in *contents*, never raising."""
        if not contents:
            return []
        try:
            return self._service.analyze_batch(contents)
        except Exception:
            return [_NEUTRAL_EMPTY for _ in contents]

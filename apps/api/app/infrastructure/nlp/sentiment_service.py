"""ModernBERT-backed sentiment analysis service.

Uses a fine-tuned text-classification pipeline from HuggingFace transformers.
Default model: tabularisai/multilingual-sentiment-analysis
  — small (≈110M params), multilingual, handles non-English without translation,
    maps to five labels that we collapse to positive/negative/neutral.

Loads lazily on first call; single module-level singleton per process (same
pattern as gliner_service.py) — safe with Celery's prefork model because each
worker process has its own copy.

Batched inference is supported via analyze_batch(); prefer it for throughput
when multiple articles arrive together.
"""

from __future__ import annotations

import threading
from typing import Any

import structlog

from app.domain.interfaces.services import SentimentResult, SentimentService

logger = structlog.get_logger(__name__)

_DEFAULT_MODEL = "tabularisai/multilingual-sentiment-analysis"
_LOCK = threading.Lock()
_pipeline_cache: dict[str, Any] = {}

# Map the five-class output → three-class label
_LABEL_MAP: dict[str, str] = {
    "very positive": "positive",
    "positive": "positive",
    "neutral": "neutral",
    "negative": "negative",
    "very negative": "negative",
}

# Short-content threshold: below this many words we flag low_confidence
_MIN_WORD_COUNT = 5


def _load_pipeline(model_id: str) -> Any:
    """Load transformers pipeline; cached by model_id (thread-safe)."""
    if model_id in _pipeline_cache:
        return _pipeline_cache[model_id]

    with _LOCK:
        if model_id in _pipeline_cache:
            return _pipeline_cache[model_id]

        import torch
        from transformers import pipeline  # type: ignore[import-untyped]

        device = 0 if torch.cuda.is_available() else -1
        logger.info("sentiment.loading_model", model_id=model_id, device=device)
        pipe = pipeline(
            "text-classification",
            model=model_id,
            device=device,
            truncation=True,
            max_length=512,
        )
        _pipeline_cache[model_id] = pipe
        logger.info("sentiment.model_loaded", model_id=model_id)
        return pipe


def _parse_result(raw: dict[str, Any], low_confidence: bool) -> SentimentResult:
    raw_label = str(raw.get("label", "neutral")).lower().strip()
    label = _LABEL_MAP.get(raw_label, "neutral")
    score = float(raw.get("score", 0.5))
    return SentimentResult(label=label, score=score, low_confidence=low_confidence)


class ModernBertSentimentService:
    """Concrete SentimentService backed by a HuggingFace text-classification pipeline.

    Parameters
    ----------
    model_id:
        HuggingFace model ID.
    """

    def __init__(self, model_id: str = _DEFAULT_MODEL) -> None:
        self._model_id = model_id

    def _pipe(self) -> Any:
        return _load_pipeline(self._model_id)

    def _is_short(self, text: str) -> bool:
        return len(text.split()) < _MIN_WORD_COUNT

    def analyze(self, text: str) -> SentimentResult:
        """Classify sentiment of a single text."""
        stripped = text.strip()
        if not stripped:
            return SentimentResult(label="neutral", score=0.5, low_confidence=True)

        low_confidence = self._is_short(stripped)
        raw: dict[str, Any] = self._pipe()(stripped)[0]
        return _parse_result(raw, low_confidence)

    def analyze_batch(self, texts: list[str]) -> list[SentimentResult]:
        """Batch sentiment classification."""
        if not texts:
            return []

        results: list[SentimentResult] = []
        non_empty_indices: list[int] = []
        non_empty_texts: list[str] = []

        for i, text in enumerate(texts):
            stripped = text.strip()
            if not stripped:
                results.append(SentimentResult(label="neutral", score=0.5, low_confidence=True))
            else:
                results.append(SentimentResult(label="neutral", score=0.5))  # placeholder
                non_empty_indices.append(i)
                non_empty_texts.append(stripped)

        if non_empty_texts:
            raw_batch: list[dict[str, Any]] = self._pipe()(non_empty_texts)
            for pos, (idx, raw) in enumerate(zip(non_empty_indices, raw_batch, strict=True)):
                results[idx] = _parse_result(raw, self._is_short(non_empty_texts[pos]))

        return results


# Static protocol conformance check
_: SentimentService = ModernBertSentimentService.__new__(ModernBertSentimentService)

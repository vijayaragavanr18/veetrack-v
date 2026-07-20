"""GLiNER-backed NER service.

Wraps the GLiNER model for named-entity recognition.  Loads lazily on first
call so import of this module is cheap.  Uses GPU when available, CPU otherwise.

The model is loaded once per process (module-level singleton) to avoid the
~2-second load penalty on every article.

Default model: urchade/gliner_small-v2.1 — a compact general-purpose NER
model that covers ORG, PER, and LOC labels well without needing GPU RAM.
"""

from __future__ import annotations

import threading
from typing import Any

import structlog
import torch

from app.domain.interfaces.services import EntityMention, NerService

logger = structlog.get_logger(__name__)

_DEFAULT_MODEL = "urchade/gliner_small-v2.1"
_LOCK = threading.Lock()
_model_cache: dict[str, Any] = {}


def _load_model(model_id: str) -> Any:
    """Load GLiNER model; cached by model_id (thread-safe)."""
    if model_id in _model_cache:
        return _model_cache[model_id]

    with _LOCK:
        if model_id in _model_cache:
            return _model_cache[model_id]

        from gliner import GLiNER  # type: ignore[import-untyped]

        device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info("gliner.loading_model", model_id=model_id, device=device)
        model = GLiNER.from_pretrained(model_id, map_location=device)
        model.eval()
        _model_cache[model_id] = model
        logger.info("gliner.model_loaded", model_id=model_id)
        return model


def _to_mention(raw: dict[str, Any]) -> EntityMention:
    """Convert a GLiNER result dict to an EntityMention."""
    return EntityMention(
        text=str(raw.get("text", "")),
        label=str(raw.get("label", "")),
        score=float(raw.get("score", 0.0)),
        start=int(raw.get("start", 0)),
        end=int(raw.get("end", 0)),
    )


class GlinerNerService:
    """Concrete NerService backed by GLiNER.

    Parameters
    ----------
    model_id:
        HuggingFace model ID.  Defaults to a small general-purpose model.
    threshold:
        Default confidence threshold for entity spans.
    """

    def __init__(
        self,
        model_id: str = _DEFAULT_MODEL,
        threshold: float = 0.5,
    ) -> None:
        self._model_id = model_id
        self._default_threshold = threshold

    def _model(self) -> Any:
        return _load_model(self._model_id)

    def extract(
        self,
        text: str,
        labels: list[str],
        *,
        threshold: float | None = None,
    ) -> list[EntityMention]:
        """Return entity mentions for a single text."""
        th = threshold if threshold is not None else self._default_threshold
        if not text.strip() or not labels:
            return []
        raw: list[dict[str, Any]] = self._model().predict_entities(
            text, labels, threshold=th
        )
        return [_to_mention(r) for r in raw]

    def extract_batch(
        self,
        texts: list[str],
        labels: list[str],
        *,
        threshold: float | None = None,
    ) -> list[list[EntityMention]]:
        """Return entity mentions for a list of texts."""
        th = threshold if threshold is not None else self._default_threshold
        if not texts or not labels:
            return [[] for _ in texts]
        non_empty = [t for t in texts if t.strip()]
        if not non_empty:
            return [[] for _ in texts]
        raw_batch: list[list[dict[str, Any]]] = self._model().batch_predict_entities(
            texts, labels, threshold=th
        )
        return [[_to_mention(r) for r in batch] for batch in raw_batch]


# Static protocol conformance check
_: NerService = GlinerNerService.__new__(GlinerNerService)

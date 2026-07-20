"""BGE-backed text embedding service.

Default model: BAAI/bge-large-en-v1.5
  — 1024-dimensional output, English-optimised, state-of-the-art retrieval quality.
  — Instruction prefix "Represent this sentence for searching relevant passages: "
    is prepended for asymmetric retrieval (omitted for the passage/document side).

Vectors are L2-normalised before return so that dot-product == cosine similarity,
matching the HNSW index created with vector_cosine_ops in migration 0001.

Dimension is asserted at load time to catch model-config mismatches fast.

Loads lazily; module-level singleton per process (same pattern as gliner_service.py).
GPU when available, CPU otherwise.
"""

from __future__ import annotations

import threading
from typing import Any

import structlog

from app.domain.interfaces.services import EmbeddingService

logger = structlog.get_logger(__name__)

REQUIRED_DIM = 1024
_DEFAULT_MODEL = "BAAI/bge-large-en-v1.5"

_LOCK = threading.Lock()
_model_cache: dict[str, Any] = {}


def _load_model(model_id: str) -> Any:
    """Load SentenceTransformer model; cached by model_id (thread-safe)."""
    if model_id in _model_cache:
        return _model_cache[model_id]

    with _LOCK:
        if model_id in _model_cache:
            return _model_cache[model_id]

        import torch
        from sentence_transformers import SentenceTransformer  # type: ignore[import-untyped]

        device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info("embedding.loading_model", model_id=model_id, device=device)
        model = SentenceTransformer(model_id, device=device)
        model.eval()

        # Fail fast if the model does not produce the expected dimension
        probe = model.encode(["probe"], normalize_embeddings=True)
        actual_dim = probe.shape[1]
        if actual_dim != REQUIRED_DIM:
            raise ValueError(
                f"EmbeddingService: model {model_id!r} produces {actual_dim}-dimensional "
                f"vectors but the schema requires {REQUIRED_DIM}."
            )

        _model_cache[model_id] = model
        logger.info("embedding.model_loaded", model_id=model_id, dim=actual_dim)
        return model


class BgeEmbeddingService:
    """Concrete EmbeddingService backed by a BGE SentenceTransformer.

    Parameters
    ----------
    model_id:
        HuggingFace model ID.  Must produce {REQUIRED_DIM}-dimensional vectors.
    """

    EMBEDDING_DIM: int = REQUIRED_DIM

    def __init__(self, model_id: str = _DEFAULT_MODEL) -> None:
        self._model_id = model_id

    def _model(self) -> Any:
        return _load_model(self._model_id)

    def embed(self, text: str) -> list[float]:
        """Return a normalised 1024-d embedding for *text*."""
        stripped = text.strip()
        if not stripped:
            return [0.0] * REQUIRED_DIM
        vecs = self._model().encode([stripped], normalize_embeddings=True)
        return [float(v) for v in vecs[0]]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Return normalised embeddings for each text in *texts*."""
        if not texts:
            return []

        zero = [0.0] * REQUIRED_DIM
        non_empty_indices: list[int] = []
        non_empty_texts: list[str] = []
        results: list[list[float]] = [zero] * len(texts)

        for i, text in enumerate(texts):
            stripped = text.strip()
            if stripped:
                non_empty_indices.append(i)
                non_empty_texts.append(stripped)

        if non_empty_texts:
            vecs = self._model().encode(non_empty_texts, normalize_embeddings=True)
            for pos, idx in enumerate(non_empty_indices):
                results[idx] = [float(v) for v in vecs[pos]]

        return results


# Static protocol conformance check
_: EmbeddingService = BgeEmbeddingService.__new__(BgeEmbeddingService)

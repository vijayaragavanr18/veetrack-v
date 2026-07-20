"""Embedding orchestration use case.

Wraps EmbeddingService to:
  - Guard against empty/whitespace content (returns zero vector with a flag).
  - Provide a batch path for throughput.

No infrastructure imports — depends only on app.domain.interfaces.services.EmbeddingService.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.interfaces.services import EmbeddingService


@dataclass
class EmbedResult:
    """Embedding result for a single article."""

    vector: list[float]
    dim: int
    skipped: bool = False  # True when content was empty; vector is all zeros


class EmbedArticle:
    """Produces a normalised embedding vector for article content.

    Parameters
    ----------
    service:
        An EmbeddingService implementation (injected by the caller).
    """

    def __init__(self, service: EmbeddingService) -> None:
        self._service = service

    def run(self, content: str) -> EmbedResult:
        """Return an EmbedResult for *content*, never raising."""
        stripped = content.strip() if content else ""
        if not stripped:
            dim = self._service.EMBEDDING_DIM
            return EmbedResult(vector=[0.0] * dim, dim=dim, skipped=True)
        try:
            vec = self._service.embed(stripped)
            return EmbedResult(vector=vec, dim=len(vec))
        except Exception:
            dim = self._service.EMBEDDING_DIM
            return EmbedResult(vector=[0.0] * dim, dim=dim, skipped=True)

    def run_batch(self, contents: list[str]) -> list[EmbedResult]:
        """Return EmbedResults for each item in *contents*, never raising."""
        if not contents:
            return []
        try:
            vecs = self._service.embed_batch(contents)
            results: list[EmbedResult] = []
            for text, vec in zip(contents, vecs, strict=True):
                skipped = not text.strip()
                results.append(EmbedResult(vector=vec, dim=len(vec), skipped=skipped))
            return results
        except Exception:
            dim = self._service.EMBEDDING_DIM
            return [EmbedResult(vector=[0.0] * dim, dim=dim, skipped=True) for _ in contents]

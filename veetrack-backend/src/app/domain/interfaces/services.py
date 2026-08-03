"""Service gateway interface Protocols.

Abstractions over external services (LLM, cache, object storage).
The application layer depends on these Protocols; infrastructure implements them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass
class EntityMention:
    """A single named-entity span extracted from text by a NER model."""

    text: str
    label: str
    score: float
    start: int = 0
    end: int = 0


@runtime_checkable
class NerService(Protocol):
    """Named-entity recognition service — backed by GLiNER (or a stub in tests)."""

    def extract(
        self,
        text: str,
        labels: list[str],
        *,
        threshold: float = 0.5,
    ) -> list[EntityMention]:
        """Extract entity mentions from *text* for the given *labels*."""
        ...

    def extract_batch(
        self,
        texts: list[str],
        labels: list[str],
        *,
        threshold: float = 0.5,
    ) -> list[list[EntityMention]]:
        """Batch variant: extract mentions for each text in *texts*."""
        ...


@runtime_checkable
class CacheGateway(Protocol):
    """Key-value cache abstraction (backed by Redis in production)."""

    async def get(self, key: str) -> bytes | None:
        """Return the cached bytes for key, or None on miss."""
        ...

    async def set(self, key: str, value: bytes, ttl_seconds: int = 300) -> None:
        """Store value under key with an optional TTL."""
        ...

    async def delete(self, key: str) -> None:
        """Remove a key from the cache (no-op if absent)."""
        ...

    async def ping(self) -> bool:
        """Return True if the cache backend is reachable, False otherwise."""
        ...


@runtime_checkable
class TaskDispatcher(Protocol):
    """Async task dispatch abstraction (backed by Celery in production).

    The application layer uses this to enqueue background work without
    importing Celery directly — keeps the domain decoupled from the broker.
    """

    def send(
        self,
        task_name: str,
        *,
        args: tuple[Any, ...] = (),
        kwargs: dict[str, Any] | None = None,
        queue: str | None = None,
    ) -> str:
        """Enqueue a named task and return its task_id."""
        ...


@dataclass
class SentimentResult:
    """Sentiment classification output for a single text."""

    label: str  # "positive" | "negative" | "neutral"
    score: float  # confidence in [0.0, 1.0]
    low_confidence: bool = False  # True when content was empty/too short


@runtime_checkable
class SentimentService(Protocol):
    """Sentiment analysis service — backed by ModernBERT (or a stub in tests)."""

    def analyze(self, text: str) -> SentimentResult:
        """Classify sentiment of a single *text*."""
        ...

    def analyze_batch(self, texts: list[str]) -> list[SentimentResult]:
        """Batch variant: classify sentiment for each text in *texts*."""
        ...


@runtime_checkable
class EmbeddingService(Protocol):
    """Text embedding service — backed by BGE (or a stub in tests).

    All concrete implementations must L2-normalise output vectors so that
    dot-product and cosine similarity are equivalent, consistent with the
    HNSW index created with ``vector_cosine_ops``.
    """

    EMBEDDING_DIM: int

    def embed(self, text: str) -> list[float]:
        """Return a normalised embedding vector for *text*."""
        ...

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Return normalised embedding vectors for each text in *texts*."""
        ...


@runtime_checkable
class LLMGateway(Protocol):
    """LLM provider abstraction — swappable between hosted API and local Ollama.

    Phase 16 adds the concrete implementations. This Protocol ensures the application
    layer is never coupled to a specific provider's SDK.
    """

    async def complete(
        self,
        prompt: str,
        *,
        system: str = "",
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> str:
        """Send a prompt and return the model's completion text."""
        ...

    async def complete_json(
        self,
        prompt: str,
        schema: dict[str, Any],
        *,
        system: str = "",
        max_tokens: int = 2048,
    ) -> dict[str, Any]:
        """Send a prompt and return a validated JSON object matching schema."""
        ...

    @property
    def model_name(self) -> str:
        """Return the identifier of the model backing this gateway."""
        ...

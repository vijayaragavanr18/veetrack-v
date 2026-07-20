"""Unit tests: BgeEmbeddingService — mocked SentenceTransformer."""

from __future__ import annotations

import math
from unittest.mock import MagicMock, patch

import pytest

from app.domain.interfaces.services import EmbeddingService
from app.infrastructure.nlp.embedding_service import (
    REQUIRED_DIM,
    BgeEmbeddingService,
)

# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------

def test_embedding_service_satisfies_protocol() -> None:
    assert isinstance(BgeEmbeddingService.__new__(BgeEmbeddingService), EmbeddingService)


def test_embedding_dim_constant_is_1024() -> None:
    assert REQUIRED_DIM == 1024
    assert BgeEmbeddingService.EMBEDDING_DIM == 1024


# ---------------------------------------------------------------------------
# Helper: build service with mock model
# ---------------------------------------------------------------------------

import numpy as np  # noqa: E402


def _unit_vec(dim: int = REQUIRED_DIM) -> list[float]:
    """Return a unit vector (all equal components, L2-normalised)."""
    v = np.ones(dim, dtype=np.float32)
    v /= np.linalg.norm(v)
    return v.tolist()


def _make_service(encode_return: np.ndarray | None = None) -> BgeEmbeddingService:
    if encode_return is None:
        encode_return = np.array([_unit_vec()])

    mock_model = MagicMock()
    mock_model.encode.return_value = encode_return

    svc = BgeEmbeddingService.__new__(BgeEmbeddingService)
    svc._model_id = "test-model"
    svc._model = lambda: mock_model  # type: ignore[method-assign]
    return svc


# ---------------------------------------------------------------------------
# embed — single text
# ---------------------------------------------------------------------------

def test_embed_returns_correct_dimension() -> None:
    svc = _make_service()
    vec = svc.embed("Tesla quarterly earnings beat expectations.")
    assert len(vec) == REQUIRED_DIM


def test_embed_returns_list_of_floats() -> None:
    svc = _make_service()
    vec = svc.embed("Some news article content here.")
    assert all(isinstance(v, float) for v in vec)


def test_embed_empty_string_returns_zero_vector() -> None:
    svc = _make_service()
    vec = svc.embed("")
    assert len(vec) == REQUIRED_DIM
    assert all(v == 0.0 for v in vec)
    # Model should not be called for empty input
    svc._model().encode.assert_not_called()  # type: ignore[attr-defined]


def test_embed_whitespace_only_returns_zero_vector() -> None:
    svc = _make_service()
    vec = svc.embed("   ")
    assert all(v == 0.0 for v in vec)


def test_embed_vector_is_l2_normalised() -> None:
    svc = _make_service()
    vec = svc.embed("Tesla reports record revenue for Q3 2024.")
    norm = math.sqrt(sum(v * v for v in vec))
    assert norm == pytest.approx(1.0, abs=1e-5)


# ---------------------------------------------------------------------------
# embed_batch
# ---------------------------------------------------------------------------

def test_embed_batch_empty_list() -> None:
    svc = _make_service()
    assert svc.embed_batch([]) == []


def test_embed_batch_returns_correct_count() -> None:
    two_vecs = np.array([_unit_vec(), _unit_vec()])
    svc = _make_service(two_vecs)
    results = svc.embed_batch(["Article one.", "Article two."])
    assert len(results) == 2
    assert all(len(v) == REQUIRED_DIM for v in results)


def test_embed_batch_empty_strings_get_zero_vectors() -> None:
    one_vec = np.array([_unit_vec()])
    mock_model = MagicMock()
    mock_model.encode.return_value = one_vec

    svc = BgeEmbeddingService.__new__(BgeEmbeddingService)
    svc._model_id = "test-model"
    svc._model = lambda: mock_model  # type: ignore[method-assign]

    results = svc.embed_batch(["", "Non-empty article.", ""])
    assert len(results) == 3
    assert all(v == 0.0 for v in results[0])   # empty → zeros
    assert all(v == 0.0 for v in results[2])   # empty → zeros
    assert any(v != 0.0 for v in results[1])   # non-empty → model output


def test_embed_batch_all_empty_does_not_call_model() -> None:
    mock_model = MagicMock()
    svc = BgeEmbeddingService.__new__(BgeEmbeddingService)
    svc._model_id = "test-model"
    svc._model = lambda: mock_model  # type: ignore[method-assign]

    svc.embed_batch(["", "   "])
    mock_model.encode.assert_not_called()


# ---------------------------------------------------------------------------
# Dimension mismatch at load time
# ---------------------------------------------------------------------------

def test_load_fails_on_wrong_dimension() -> None:
    import numpy as np

    wrong_dim = 768
    mock_model = MagicMock()
    mock_model.encode.return_value = np.ones((1, wrong_dim), dtype=np.float32)

    with (
        patch("app.infrastructure.nlp.embedding_service._model_cache", {}),
        patch(
            "app.infrastructure.nlp.embedding_service._LOCK",
            __enter__=lambda s: None,
            __exit__=lambda s, *a: None,
        ),
        patch("torch.cuda.is_available", return_value=False),
        patch(
            "sentence_transformers.SentenceTransformer",
            return_value=mock_model,
        ),pytest.raises(ValueError, match="1024")
    ):
        from app.infrastructure.nlp.embedding_service import _load_model
        _load_model("some-768d-model")

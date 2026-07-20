"""Unit tests: embed_article task — mocked SentenceTransformer, no GPU/download."""

from __future__ import annotations

import math
import time
from typing import Any
from unittest.mock import MagicMock

import numpy as np
import pytest

from workers.tasks.nlp.embed_article import REQUIRED_DIM, _embed_text


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

def test_required_dim_is_1024() -> None:
    assert REQUIRED_DIM == 1024


# ---------------------------------------------------------------------------
# _embed_text helper
# ---------------------------------------------------------------------------

def _unit_vec(dim: int = REQUIRED_DIM) -> "np.ndarray":
    v = np.ones(dim, dtype=np.float32)
    v /= np.linalg.norm(v)
    return v


def _make_model(vec: "np.ndarray | None" = None) -> Any:
    if vec is None:
        vec = _unit_vec()
    m = MagicMock()
    m.encode.return_value = np.array([vec])
    return m


def test_embed_text_correct_length() -> None:
    model = _make_model()
    result = _embed_text(model, "Tesla announces record revenue for Q3 2024.")
    assert len(result) == REQUIRED_DIM


def test_embed_text_returns_floats() -> None:
    model = _make_model()
    result = _embed_text(model, "Some news article content.")
    assert all(isinstance(v, float) for v in result)


def test_embed_text_empty_returns_zeros() -> None:
    model = _make_model()
    result = _embed_text(model, "")
    assert len(result) == REQUIRED_DIM
    assert all(v == 0.0 for v in result)
    model.encode.assert_not_called()


def test_embed_text_whitespace_returns_zeros() -> None:
    model = _make_model()
    result = _embed_text(model, "   ")
    assert all(v == 0.0 for v in result)
    model.encode.assert_not_called()


def test_embed_text_vector_is_l2_normalised() -> None:
    model = _make_model()
    result = _embed_text(model, "Breaking news: Apple surpasses $3 trillion market cap.")
    norm = math.sqrt(sum(v * v for v in result))
    assert norm == pytest.approx(1.0, abs=1e-5)


# ---------------------------------------------------------------------------
# Dimension mismatch raises ValueError
# ---------------------------------------------------------------------------

def test_dimension_mismatch_raises() -> None:
    import numpy as np
    from unittest.mock import patch

    wrong_dim = 768
    mock_model = MagicMock()
    mock_model.encode.return_value = np.ones((1, wrong_dim), dtype=np.float32)

    with (
        patch("workers.tasks.nlp.embed_article._embedding_model", None),
        patch("workers.tasks.nlp.embed_article._embedding_model_id", ""),
        patch("torch.cuda.is_available", return_value=False),
        patch("sentence_transformers.SentenceTransformer", return_value=mock_model),
    ):
        with pytest.raises(ValueError, match="1024"):
            from workers.tasks.nlp.embed_article import _get_model
            _get_model("some-768d-model")


# ---------------------------------------------------------------------------
# Batch throughput benchmark
# ---------------------------------------------------------------------------

def test_batch_faster_than_one_at_a_time() -> None:
    """Batch encode(list) must be faster than N individual encode() calls."""
    DELAY_PER_CALL_S = 0.010
    texts = [f"Article {i}: substantive news content about market events." for i in range(20)]

    def _slow_encode(inputs: Any, normalize_embeddings: bool = False) -> "np.ndarray":
        if isinstance(inputs, list):
            time.sleep(DELAY_PER_CALL_S)
            return np.array([_unit_vec() for _ in inputs])
        else:
            time.sleep(DELAY_PER_CALL_S)
            return np.array([_unit_vec()])

    # one-at-a-time
    model = MagicMock()
    model.encode = _slow_encode
    t0 = time.perf_counter()
    for text in texts:
        _embed_text(model, text)
    one_at_a_time_s = time.perf_counter() - t0

    # batch
    t0 = time.perf_counter()
    model.encode(texts, normalize_embeddings=True)
    batch_s = time.perf_counter() - t0

    print(
        f"\n[benchmark] one-at-a-time: {one_at_a_time_s*1000:.1f} ms | "
        f"batch: {batch_s*1000:.1f} ms | "
        f"speedup: {one_at_a_time_s / batch_s:.1f}×"
    )
    assert batch_s < one_at_a_time_s, (
        f"Batch ({batch_s*1000:.1f} ms) should be faster than "
        f"one-at-a-time ({one_at_a_time_s*1000:.1f} ms)"
    )

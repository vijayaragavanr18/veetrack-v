"""Unit tests: EmbedArticle use case — pure logic, no real model."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.application.use_cases.embeddings.embed_article import EmbedArticle

REQUIRED_DIM = 1024


def _unit_vec(dim: int = REQUIRED_DIM) -> list[float]:
    import math
    v = 1.0 / math.sqrt(dim)
    return [v] * dim


def _stub_service(vec: list[float] | None = None) -> MagicMock:
    if vec is None:
        vec = _unit_vec()
    svc = MagicMock()
    svc.EMBEDDING_DIM = REQUIRED_DIM
    svc.embed.return_value = vec
    svc.embed_batch.return_value = [vec]
    return svc


# ---------------------------------------------------------------------------
# run (single article)
# ---------------------------------------------------------------------------

def test_run_returns_correct_dimension() -> None:
    uc = EmbedArticle(_stub_service())
    result = uc.run("Tesla reports record Q3 results across all segments.")
    assert result.dim == REQUIRED_DIM
    assert len(result.vector) == REQUIRED_DIM


def test_run_not_skipped_for_real_content() -> None:
    uc = EmbedArticle(_stub_service())
    result = uc.run("Some non-empty news article.")
    assert not result.skipped


def test_run_empty_content_returns_zero_vector_skipped() -> None:
    uc = EmbedArticle(_stub_service())
    result = uc.run("")
    assert result.skipped is True
    assert all(v == 0.0 for v in result.vector)
    uc._service.embed.assert_not_called()  # type: ignore[attr-defined]


def test_run_whitespace_content_skipped() -> None:
    uc = EmbedArticle(_stub_service())
    result = uc.run("   \n  ")
    assert result.skipped is True


def test_run_service_exception_returns_zero_vector_skipped() -> None:
    svc = MagicMock()
    svc.EMBEDDING_DIM = REQUIRED_DIM
    svc.embed.side_effect = RuntimeError("model crashed")
    uc = EmbedArticle(svc)
    result = uc.run("Some content.")
    assert result.skipped is True
    assert all(v == 0.0 for v in result.vector)


# ---------------------------------------------------------------------------
# run_batch
# ---------------------------------------------------------------------------

def test_run_batch_empty_list() -> None:
    uc = EmbedArticle(_stub_service())
    assert uc.run_batch([]) == []


def test_run_batch_returns_correct_count() -> None:
    svc = MagicMock()
    svc.EMBEDDING_DIM = REQUIRED_DIM
    v1, v2 = _unit_vec(), _unit_vec()
    svc.embed_batch.return_value = [v1, v2]
    uc = EmbedArticle(svc)
    results = uc.run_batch(["Article one.", "Article two."])
    assert len(results) == 2
    assert all(r.dim == REQUIRED_DIM for r in results)


def test_run_batch_marks_empty_items_skipped() -> None:
    svc = MagicMock()
    svc.EMBEDDING_DIM = REQUIRED_DIM
    # embed_batch is called with non-empty items but returns a vector per item
    svc.embed_batch.return_value = [_unit_vec(), _unit_vec(), _unit_vec()]
    uc = EmbedArticle(svc)
    results = uc.run_batch(["", "Real content.", ""])
    # skipped is derived from whether the text was empty, not from the vector
    assert results[0].skipped is True
    assert results[2].skipped is True
    assert results[1].skipped is False


def test_run_batch_exception_returns_all_skipped() -> None:
    svc = MagicMock()
    svc.EMBEDDING_DIM = REQUIRED_DIM
    svc.embed_batch.side_effect = RuntimeError("GPU OOM")
    uc = EmbedArticle(svc)
    results = uc.run_batch(["a", "b", "c"])
    assert len(results) == 3
    assert all(r.skipped and all(v == 0.0 for v in r.vector) for r in results)

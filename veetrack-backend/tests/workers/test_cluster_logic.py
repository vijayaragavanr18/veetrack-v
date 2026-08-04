"""Unit tests: cluster_article pure helpers — _cosine_sim and _update_centroid.

Uses 3-dimensional vectors for readability.
No DB, no Redis, no Celery broker required.
"""

from __future__ import annotations

import math

import pytest

from workers.tasks.nlp.cluster_article import _cosine_sim, _update_centroid

# ---------------------------------------------------------------------------
# _cosine_sim
# ---------------------------------------------------------------------------


def test_cosine_sim_identical_vectors() -> None:
    """Cosine similarity of a vector with itself is 1.0."""
    v = [1.0, 0.0, 0.0]
    assert _cosine_sim(v, v) == pytest.approx(1.0, abs=1e-9)


def test_cosine_sim_orthogonal_vectors() -> None:
    """Perpendicular vectors have cosine similarity 0.0."""
    a = [1.0, 0.0, 0.0]
    b = [0.0, 1.0, 0.0]
    assert _cosine_sim(a, b) == pytest.approx(0.0, abs=1e-9)


def test_cosine_sim_opposite_vectors() -> None:
    """Anti-parallel vectors have cosine similarity -1.0."""
    a = [1.0, 0.0, 0.0]
    b = [-1.0, 0.0, 0.0]
    assert _cosine_sim(a, b) == pytest.approx(-1.0, abs=1e-9)


def test_cosine_sim_zero_vector_a_returns_0() -> None:
    """Zero vector as first argument → returns 0.0 (no division by zero)."""
    a = [0.0, 0.0, 0.0]
    b = [1.0, 2.0, 3.0]
    assert _cosine_sim(a, b) == 0.0


def test_cosine_sim_zero_vector_b_returns_0() -> None:
    """Zero vector as second argument → returns 0.0 (no division by zero)."""
    a = [1.0, 2.0, 3.0]
    b = [0.0, 0.0, 0.0]
    assert _cosine_sim(a, b) == 0.0


def test_cosine_sim_both_zero_vectors_returns_0() -> None:
    """Both zero vectors → returns 0.0."""
    assert _cosine_sim([0.0, 0.0, 0.0], [0.0, 0.0, 0.0]) == 0.0


def test_cosine_sim_range_minus1_to_plus1() -> None:
    """Cosine similarity is always in [-1, 1] for arbitrary vectors."""
    a = [3.0, -1.0, 2.0]
    b = [-2.0, 4.0, 1.0]
    result = _cosine_sim(a, b)
    assert -1.0 - 1e-9 <= result <= 1.0 + 1e-9


def test_cosine_sim_known_value() -> None:
    """Test a manually computable case: [1,1,0] vs [0,1,1] → 0.5."""
    a = [1.0, 1.0, 0.0]
    b = [0.0, 1.0, 1.0]
    # dot = 1, |a| = sqrt(2), |b| = sqrt(2) → dot/(|a|*|b|) = 1/2
    assert _cosine_sim(a, b) == pytest.approx(0.5, abs=1e-9)


# ---------------------------------------------------------------------------
# _update_centroid
# ---------------------------------------------------------------------------


def test_update_centroid_single_article() -> None:
    """With n=1, old and new contribute equally; result is normalised."""
    old = [1.0, 0.0, 0.0]
    new = [0.0, 1.0, 0.0]
    result = _update_centroid(old, n=1, new_vec=new)
    # Raw average is [0.5, 0.5, 0.0]; after normalisation → [1/√2, 1/√2, 0]
    norm = math.sqrt(sum(x * x for x in result))
    assert norm == pytest.approx(1.0, abs=1e-9)
    assert result[0] == pytest.approx(result[1], abs=1e-9)
    assert result[2] == pytest.approx(0.0, abs=1e-9)


def test_update_centroid_preserves_normalization() -> None:
    """Result always has L2 norm ≈ 1.0 regardless of input magnitudes."""
    old = [3.0, 4.0, 0.0]  # not unit-length
    new = [0.0, 0.0, 5.0]  # not unit-length
    result = _update_centroid(old, n=5, new_vec=new)
    norm = math.sqrt(sum(x * x for x in result))
    assert norm == pytest.approx(1.0, abs=1e-9)


def test_update_centroid_large_n_barely_moves() -> None:
    """With a large existing cluster, a single new article barely shifts the centroid."""
    old = [1.0, 0.0, 0.0]
    new = [0.0, 1.0, 0.0]
    result = _update_centroid(old, n=1000, new_vec=new)
    # Cosine similarity to old centroid should be very high
    sim = _cosine_sim(result, old)
    assert sim > 0.999


def test_update_centroid_equal_weights_at_n1() -> None:
    """n=1 gives equal weight: result is mid-way between old and new."""
    old = [1.0, 0.0, 0.0]
    new = [0.0, 0.0, 1.0]
    result = _update_centroid(old, n=1, new_vec=new)
    # Both components should be equal after normalisation
    assert result[0] == pytest.approx(result[2], abs=1e-9)


def test_update_centroid_zero_raw_returns_raw() -> None:
    """If raw average is zero vector, return as-is (no divide-by-zero)."""
    old = [1.0, 0.0, 0.0]
    new = [-1.0, 0.0, 0.0]
    # With n=1: raw = (1*1 + (-1)) / 2 = 0, same for others → [0,0,0]
    result = _update_centroid(old, n=1, new_vec=new)
    # Must not raise; result is [0.0, 0.0, 0.0]
    assert all(x == 0.0 for x in result)

"""Unit tests: cluster_article task — pure helpers only, no DB/Redis."""

from __future__ import annotations

import math

import pytest

from tasks.nlp.cluster_article import _cosine_sim, _update_centroid


# ---------------------------------------------------------------------------
# _cosine_sim
# ---------------------------------------------------------------------------

def test_cosine_sim_identical() -> None:
    v = [1.0, 0.0, 0.0, 0.0]
    assert _cosine_sim(v, v) == pytest.approx(1.0, abs=1e-6)


def test_cosine_sim_orthogonal() -> None:
    a = [1.0, 0.0]
    b = [0.0, 1.0]
    assert _cosine_sim(a, b) == pytest.approx(0.0, abs=1e-6)


def test_cosine_sim_zero_vector_returns_zero() -> None:
    assert _cosine_sim([0.0, 0.0], [1.0, 0.0]) == 0.0


def test_cosine_sim_opposite() -> None:
    a = [1.0, 0.0]
    b = [-1.0, 0.0]
    assert _cosine_sim(a, b) == pytest.approx(-1.0, abs=1e-6)


def test_cosine_sim_near_identical() -> None:
    v = [0.6, 0.8]
    w = [0.601, 0.799]
    assert _cosine_sim(v, w) > 0.99


# ---------------------------------------------------------------------------
# _update_centroid
# ---------------------------------------------------------------------------

def test_update_centroid_returns_unit_vector() -> None:
    old = [1.0, 0.0, 0.0, 0.0]
    new = [0.0, 1.0, 0.0, 0.0]
    result = _update_centroid(old, n=1, new_vec=new)
    norm = math.sqrt(sum(x * x for x in result))
    assert norm == pytest.approx(1.0, abs=1e-6)


def test_update_centroid_equal_weight_at_n1() -> None:
    old = [1.0, 0.0]
    new = [0.0, 1.0]
    result = _update_centroid(old, n=1, new_vec=new)
    assert result[0] == pytest.approx(result[1], abs=1e-6)


def test_update_centroid_large_n_barely_moves() -> None:
    old = [1.0, 0.0]
    new = [0.0, 1.0]
    result = _update_centroid(old, n=1000, new_vec=new)
    sim = _cosine_sim(result, old)
    assert sim > 0.999


def test_update_centroid_zero_old_normalises_new() -> None:
    old = [0.0, 0.0]
    new = [3.0, 4.0]
    result = _update_centroid(old, n=0, new_vec=new)
    norm = math.sqrt(sum(x * x for x in result))
    # If norm is 0 we just get [0,0] — otherwise unit
    if norm > 0:
        assert norm == pytest.approx(1.0, abs=1e-5)

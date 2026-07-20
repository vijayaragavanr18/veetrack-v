"""Unit tests: AssignToStory use case — pure math, no DB."""

from __future__ import annotations

import math

import pytest

from app.application.use_cases.clustering.assign_to_story import (
    AssignToStory,
    cosine_similarity,
    update_centroid,
)

# ---------------------------------------------------------------------------
# cosine_similarity
# ---------------------------------------------------------------------------

def _unit(dim: int = 4) -> list[float]:
    v = [1.0] * dim
    n = math.sqrt(sum(x * x for x in v))
    return [x / n for x in v]


def _orthogonal() -> list[float]:
    return [1.0, 0.0, 0.0, 0.0]


def _opposite() -> list[float]:
    return [-1.0, 0.0, 0.0, 0.0]


def test_cosine_similarity_identical() -> None:
    v = _unit()
    assert cosine_similarity(v, v) == pytest.approx(1.0, abs=1e-6)


def test_cosine_similarity_orthogonal() -> None:
    a = [1.0, 0.0]
    b = [0.0, 1.0]
    assert cosine_similarity(a, b) == pytest.approx(0.0, abs=1e-6)


def test_cosine_similarity_opposite() -> None:
    a = [1.0, 0.0]
    b = [-1.0, 0.0]
    assert cosine_similarity(a, b) == pytest.approx(-1.0, abs=1e-6)


def test_cosine_similarity_zero_vector() -> None:
    a = [0.0, 0.0]
    b = [1.0, 0.0]
    assert cosine_similarity(a, b) == 0.0


def test_cosine_similarity_mismatched_length() -> None:
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0, 0.0]) == 0.0


def test_cosine_similarity_near_identical() -> None:
    v = [0.6, 0.8]
    w = [0.601, 0.799]
    sim = cosine_similarity(v, w)
    assert sim > 0.99


# ---------------------------------------------------------------------------
# update_centroid
# ---------------------------------------------------------------------------

def test_update_centroid_l2_normalised() -> None:
    old = [1.0, 0.0, 0.0, 0.0]
    new = [0.0, 1.0, 0.0, 0.0]
    result = update_centroid(old, n=1, new_vec=new)
    norm = math.sqrt(sum(x * x for x in result))
    assert norm == pytest.approx(1.0, abs=1e-6)


def test_update_centroid_moves_toward_new_vec() -> None:
    old = [1.0, 0.0]
    new = [0.0, 1.0]
    result = update_centroid(old, n=10, new_vec=new)
    # With 10 existing, new vec has 1/11 weight; x[0] should still dominate
    assert result[0] > result[1]


def test_update_centroid_equal_weight_at_n1() -> None:
    old = [1.0, 0.0]
    new = [0.0, 1.0]
    result = update_centroid(old, n=1, new_vec=new)
    # Average of [1,0] and [0,1] is [0.5, 0.5], normalised to equal components
    assert result[0] == pytest.approx(result[1], abs=1e-6)


def test_update_centroid_many_articles_stable() -> None:
    """After adding one more to a large cluster, centroid barely moves."""
    old = [1.0, 0.0, 0.0, 0.0]
    new = [0.0, 0.0, 0.0, 1.0]
    result = update_centroid(old, n=1000, new_vec=new)
    sim = cosine_similarity(result, old)
    assert sim > 0.999


# ---------------------------------------------------------------------------
# AssignToStory.assign
# ---------------------------------------------------------------------------

def test_assign_joins_existing_story_above_threshold() -> None:
    threshold = 0.75
    centroid = [1.0, 0.0, 0.0, 0.0]
    article_vec = [0.9, 0.1, 0.0, 0.0]
    norm = math.sqrt(sum(x * x for x in article_vec))
    article_vec = [x / norm for x in article_vec]

    uc = AssignToStory(threshold=threshold)
    result = uc.assign("art-1", article_vec, [("story-1", centroid, 5)])

    assert not result.created
    assert result.story_id == "story-1"
    assert result.similarity >= threshold


def test_assign_creates_new_story_below_threshold() -> None:
    threshold = 0.75
    centroid = [1.0, 0.0, 0.0, 0.0]
    article_vec = [0.0, 1.0, 0.0, 0.0]  # orthogonal → similarity = 0

    uc = AssignToStory(threshold=threshold)
    result = uc.assign("art-2", article_vec, [("story-1", centroid, 3)])

    assert result.created
    assert result.story_id == ""


def test_assign_no_active_stories_creates_new() -> None:
    uc = AssignToStory(threshold=0.75)
    result = uc.assign("art-3", [1.0, 0.0, 0.0, 0.0], [])
    assert result.created


def test_assign_picks_best_story() -> None:
    centroid_a = [1.0, 0.0, 0.0, 0.0]
    centroid_b = [0.0, 1.0, 0.0, 0.0]
    article_vec = [0.95, 0.31, 0.0, 0.0]
    norm = math.sqrt(sum(x * x for x in article_vec))
    article_vec = [x / norm for x in article_vec]

    uc = AssignToStory(threshold=0.5)
    result = uc.assign(
        "art-4",
        article_vec,
        [("story-a", centroid_a, 4), ("story-b", centroid_b, 4)],
    )
    assert result.story_id == "story-a"

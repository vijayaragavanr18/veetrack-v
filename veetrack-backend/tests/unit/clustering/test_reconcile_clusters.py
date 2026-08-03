"""Unit tests: ReconcileClusters use case.

Strategy:
  - HDBSCAN smoke tests use clearly-separated, non-duplicate 2D data.
  - ReconcileClusters.reconcile() tests mock run_hdbscan so we verify pure
    dict-manipulation logic independently of HDBSCAN's clustering behaviour.
"""

from __future__ import annotations

import math
from unittest.mock import patch

import numpy as np
import pytest

from app.application.use_cases.clustering.assign_to_story import update_centroid
from app.application.use_cases.clustering.reconcile_clusters import (
    ReconcileClusters,
    run_hdbscan,
)

# ---------------------------------------------------------------------------
# update_centroid (shared pure helper)
# ---------------------------------------------------------------------------


def test_update_centroid_normalised() -> None:
    old = [1.0, 0.0, 0.0, 0.0]
    new = [0.0, 1.0, 0.0, 0.0]
    result = update_centroid(old, n=1, new_vec=new)
    norm = math.sqrt(sum(x * x for x in result))
    assert norm == pytest.approx(1.0, abs=1e-6)


# ---------------------------------------------------------------------------
# run_hdbscan smoke tests — well-separated 2D data
# ---------------------------------------------------------------------------


def _two_cluster_data() -> np.ndarray:
    """Two clearly-separated groups: 5 near x=1 and 5 near y=1."""
    a = np.zeros((5, 2), dtype=np.float32)
    a[:, 0] = np.linspace(0.90, 1.10, 5)
    a[:, 1] = 0.0

    b = np.zeros((5, 2), dtype=np.float32)
    b[:, 0] = 0.0
    b[:, 1] = np.linspace(0.90, 1.10, 5)

    return np.vstack([a, b])


def test_run_hdbscan_returns_integer_labels() -> None:
    embs = _two_cluster_data()
    labels, probs = run_hdbscan(embs, min_cluster_size=3, min_samples=1)
    assert labels.shape == (10,)
    assert probs.shape == (10,)
    assert np.issubdtype(labels.dtype, np.integer)


def test_run_hdbscan_finds_two_clusters() -> None:
    embs = _two_cluster_data()
    labels, _ = run_hdbscan(embs, min_cluster_size=3, min_samples=1)
    unique_real = {lb for lb in labels.tolist() if lb != -1}
    assert len(unique_real) == 2


def test_run_hdbscan_noise_label_is_minus_one() -> None:
    """Two isolated points cannot form a cluster with min_cluster_size=3 → noise."""
    embs = np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)
    labels, _ = run_hdbscan(embs, min_cluster_size=3, min_samples=1)
    assert all(lb == -1 for lb in labels.tolist())


# ---------------------------------------------------------------------------
# ReconcileClusters — merge scenario (mocked HDBSCAN)
# ---------------------------------------------------------------------------


def _dummy_emb(n: int) -> np.ndarray:
    return np.zeros((n, 4), dtype=np.float32)


@pytest.mark.asyncio
async def test_reconcile_detects_merge() -> None:
    """When HDBSCAN puts story-a and story-b articles in the same cluster → merge."""
    article_ids = [f"a{i}" for i in range(5)] + [f"b{i}" for i in range(5)]
    embeddings = _dummy_emb(10)
    article_to_story = {f"a{i}": "story-a" for i in range(5)}
    article_to_story.update({f"b{i}": "story-b" for i in range(5)})
    # story-a has more members so it should be the merge target
    story_article_counts = {"story-a": 8, "story-b": 5}

    labels = np.zeros(10, dtype=np.intp)
    probs = np.ones(10, dtype=np.float32)
    with patch(
        "app.application.use_cases.clustering.reconcile_clusters.run_hdbscan",
        return_value=(labels, probs),
    ):
        result = await ReconcileClusters(min_cluster_size=3, min_samples=1).reconcile(
            article_ids, embeddings, article_to_story, story_article_counts
        )

    assert len(result.merges) == 1
    merge = result.merges[0]
    assert merge.target_story_id == "story-a"
    assert merge.source_story_id == "story-b"


@pytest.mark.asyncio
async def test_reconcile_detects_split() -> None:
    """When HDBSCAN splits a single story into two clusters → split op."""
    article_ids = [f"x{i}" for i in range(5)] + [f"y{i}" for i in range(5)]
    embeddings = _dummy_emb(10)
    # All articles belong to story-merged
    article_to_story = {aid: "story-merged" for aid in article_ids}
    story_article_counts = {"story-merged": 10}

    # HDBSCAN puts x-articles in cluster 0, y-articles in cluster 1
    labels = np.array([0] * 5 + [1] * 5, dtype=np.intp)
    probs = np.ones(10, dtype=np.float32)

    with patch(
        "app.application.use_cases.clustering.reconcile_clusters.run_hdbscan",
        return_value=(labels, probs),
    ):
        result = await ReconcileClusters(min_cluster_size=3, min_samples=1).reconcile(
            article_ids, embeddings, article_to_story, story_article_counts
        )

    assert len(result.splits) >= 1
    assert all(s.source_story_id == "story-merged" for s in result.splits)
    # Split articles should be from the smaller cluster
    split_articles = {aid for s in result.splits for aid in s.article_ids}
    # All split articles should belong to story-merged
    assert all(article_to_story.get(aid) == "story-merged" for aid in split_articles)


@pytest.mark.asyncio
async def test_reconcile_creates_new_story_for_unassigned() -> None:
    """Unassigned articles in the same HDBSCAN cluster → new story op."""
    article_ids = [f"new{i}" for i in range(5)]
    embeddings = _dummy_emb(5)
    article_to_story: dict[str, str] = {}  # all unassigned

    labels = np.zeros(5, dtype=np.intp)
    probs = np.ones(5, dtype=np.float32)
    with patch(
        "app.application.use_cases.clustering.reconcile_clusters.run_hdbscan",
        return_value=(labels, probs),
    ):
        result = await ReconcileClusters(min_cluster_size=3, min_samples=1).reconcile(
            article_ids, embeddings, article_to_story, {}
        )

    assert len(result.new_stories) >= 1
    new_article_ids = [aid for op in result.new_stories for aid in op.article_ids]
    assert set(new_article_ids) == set(article_ids)


@pytest.mark.asyncio
async def test_reconcile_noise_articles_collected() -> None:
    """Articles with HDBSCAN label -1 land in noise_article_ids."""
    article_ids = ["n0", "n1", "c0", "c1", "c2"]
    embeddings = _dummy_emb(5)
    article_to_story: dict[str, str] = {}

    labels = np.array([-1, -1, 0, 0, 0], dtype=np.intp)
    probs = np.ones(5, dtype=np.float32)

    with patch(
        "app.application.use_cases.clustering.reconcile_clusters.run_hdbscan",
        return_value=(labels, probs),
    ):
        result = await ReconcileClusters(min_cluster_size=3, min_samples=1).reconcile(
            article_ids, embeddings, article_to_story, {}
        )

    assert set(result.noise_article_ids) == {"n0", "n1"}


@pytest.mark.asyncio
async def test_reconcile_empty_input() -> None:
    reconciler = ReconcileClusters()
    result = await reconciler.reconcile([], np.empty((0, 4), dtype=np.float32), {}, {})
    assert result.merges == []
    assert result.splits == []
    assert result.new_stories == []
    assert result.noise_article_ids == []


@pytest.mark.asyncio
async def test_reconcile_merge_keeps_larger_story() -> None:
    """Merge always keeps the story with MORE members as target."""
    article_ids = [f"big{i}" for i in range(3)] + [f"small{i}" for i in range(3)]
    embeddings = _dummy_emb(6)
    article_to_story = {f"big{i}": "story-big" for i in range(3)}
    article_to_story.update({f"small{i}": "story-small" for i in range(3)})
    story_article_counts = {"story-big": 100, "story-small": 5}

    labels = np.zeros(6, dtype=np.intp)
    probs = np.ones(6, dtype=np.float32)
    with patch(
        "app.application.use_cases.clustering.reconcile_clusters.run_hdbscan",
        return_value=(labels, probs),
    ):
        result = await ReconcileClusters(min_cluster_size=2, min_samples=1).reconcile(
            article_ids, embeddings, article_to_story, story_article_counts
        )

    assert result.merges[0].target_story_id == "story-big"
    assert result.merges[0].source_story_id == "story-small"


@pytest.mark.asyncio
async def test_reconcile_borderline_merge_calls_agent() -> None:
    article_ids = [f"a{i}" for i in range(2)] + [f"b{i}" for i in range(2)]
    embeddings = _dummy_emb(4)
    article_to_story = {f"a{i}": "story-a" for i in range(2)}
    article_to_story.update({f"b{i}": "story-b" for i in range(2)})
    story_article_counts = {"story-a": 2, "story-b": 2}

    labels = np.zeros(4, dtype=np.intp)
    probs = np.zeros(4, dtype=np.float32) # borderline!
    
    with patch(
        "app.application.use_cases.clustering.reconcile_clusters.run_hdbscan",
        return_value=(labels, probs),
    ):
        reconciler = ReconcileClusters(min_cluster_size=2, min_samples=1, gateway="dummy", borderline_threshold=0.5)
        
        with patch.object(reconciler, "_run_agent", return_value=("keep_separate", [], False)) as mock_agent:
            result = await reconciler.reconcile(
                article_ids, embeddings, article_to_story, story_article_counts
            )
            mock_agent.assert_called_once()
            
            # Since it returns keep_separate, merges should be empty
            assert len(result.merges) == 0


@pytest.mark.asyncio
async def test_reconcile_borderline_split_calls_agent() -> None:
    article_ids = [f"a{i}" for i in range(4)]
    embeddings = _dummy_emb(4)
    article_to_story = {f"a{i}": "story-a" for i in range(4)}
    story_article_counts = {"story-a": 4}

    labels = np.array([0, 0, 1, 1], dtype=np.intp)
    probs = np.zeros(4, dtype=np.float32) # borderline!
    
    with patch(
        "app.application.use_cases.clustering.reconcile_clusters.run_hdbscan",
        return_value=(labels, probs),
    ):
        reconciler = ReconcileClusters(min_cluster_size=2, min_samples=1, gateway="dummy", borderline_threshold=0.5)
        
        with patch.object(reconciler, "_run_agent", return_value=("merge", [], False)) as mock_agent:
            result = await reconciler.reconcile(
                article_ids, embeddings, article_to_story, story_article_counts
            )
            mock_agent.assert_called_once()
            
            # Since agent says merge (keep together), splits should be empty
            assert len(result.splits) == 0

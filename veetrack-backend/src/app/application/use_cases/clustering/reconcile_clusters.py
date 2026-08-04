"""HDBSCAN-based nightly cluster reconciliation use case.

Given a matrix of (article_id, embedding) pairs from a recent time window,
runs HDBSCAN and diffs the new cluster assignments against the current
stories / story_articles state to find:

  - MERGE candidates: two existing stories that HDBSCAN now puts in the same
    cluster → union their article lists, keep the older story_id, archive the
    newer one, log to audit_log.
  - SPLIT candidates: articles from a single existing story that HDBSCAN
    now puts in different clusters → create a new story for the split-off
    group, reassign those articles, log to audit_log.
  - NEW stories: articles that have no story assignment yet and HDBSCAN
    groups together → create a new story.
  - NOISE (-1): HDBSCAN noise articles are not assigned; they stay unlinked
    until a later run.

This module has zero infrastructure imports — it receives plain Python
data structures (lists, dicts, numpy arrays) and returns operation lists
that the Celery task then executes against the DB.
"""

from __future__ import annotations

from typing import Any

from dataclasses import dataclass, field

import numpy as np

# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class MergeOp:
    """Merge *source_story_id* into *target_story_id* (keep the older one)."""

    target_story_id: str  # survives
    source_story_id: str  # archived
    article_ids: list[str] = field(default_factory=list)  # articles to reassign


@dataclass
class SplitOp:
    """Spin off *article_ids* from *source_story_id* into a new story."""

    source_story_id: str
    article_ids: list[str] = field(default_factory=list)


@dataclass
class NewStoryOp:
    """Create a brand-new story seeded with *article_ids*."""

    article_ids: list[str] = field(default_factory=list)


@dataclass
class ReconcileResult:
    merges: list[MergeOp] = field(default_factory=list)
    splits: list[SplitOp] = field(default_factory=list)
    new_stories: list[NewStoryOp] = field(default_factory=list)
    noise_article_ids: list[str] = field(default_factory=list)
    timeline_highlights: dict[str, list[str]] = field(default_factory=dict)
    is_pattern: dict[str, bool] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Pure HDBSCAN runner
# ---------------------------------------------------------------------------


def run_hdbscan(
    embeddings: np.ndarray,
    min_cluster_size: int = 3,
    min_samples: int = 2,
) -> tuple[np.ndarray, np.ndarray]:
    """Run HDBSCAN on *embeddings*; return integer label array (-1 = noise) and probabilities.

    Parameters
    ----------
    embeddings:
        Shape (n, dim) float32 matrix, L2-normalised rows.
    min_cluster_size:
        Minimum cluster size (configurable — see ReconcileSettings).
    min_samples:
        Controls conservatism: higher = more noise, fewer micro-clusters.
    """
    import hdbscan  # type: ignore[import-untyped]

    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=min_cluster_size,
        min_samples=min_samples,
        metric="euclidean",  # cosine ≡ euclidean for L2-normalised vectors
        core_dist_n_jobs=1,  # deterministic; worker has 1 core per process
    )
    clusterer.fit(embeddings)
    return clusterer.labels_, clusterer.probabilities_


# ---------------------------------------------------------------------------
# Reconcile use case
# ---------------------------------------------------------------------------


class ReconcileClusters:
    """Pure reconciliation logic — no DB access.

    Parameters
    ----------
    min_cluster_size:
        Passed to HDBSCAN.
    min_samples:
        Passed to HDBSCAN.
    """

    def __init__(
        self,
        min_cluster_size: int = 3,
        min_samples: int = 2,
        gateway: Any | None = None,
        tools: dict[str, Any] | None = None,
        borderline_threshold: float = 0.5,
    ) -> None:
        self.min_cluster_size = min_cluster_size
        self.min_samples = min_samples
        self.gateway = gateway
        self.tools = tools or {}
        self.borderline_threshold = borderline_threshold

    async def reconcile(
        self,
        article_ids: list[str],
        embeddings: np.ndarray,
        article_to_story: dict[str, str],
        story_article_counts: dict[str, int],
    ) -> ReconcileResult:
        """Diff HDBSCAN output against current story assignments.

        Parameters
        ----------
        article_ids:
            Ordered list of article IDs corresponding to rows in *embeddings*.
        embeddings:
            Shape (n, 1024) float32, L2-normalised.
        article_to_story:
            Mapping article_id → current story_id (empty string if unassigned).
        story_article_counts:
            Mapping story_id → total member count (needed to decide merge direction).

        Returns
        -------
        ReconcileResult with merge/split/new-story operations to execute.
        """
        if len(article_ids) == 0:
            return ReconcileResult()

        labels, probabilities = run_hdbscan(
            embeddings,
            min_cluster_size=self.min_cluster_size,
            min_samples=self.min_samples,
        )

        # Group article_ids and their probabilities by their HDBSCAN cluster label
        cluster_to_articles: dict[int, list[str]] = {}
        cluster_to_probs: dict[int, list[float]] = {}
        for article_id, label, prob in zip(article_ids, labels.tolist(), probabilities.tolist(), strict=True):
            cluster_to_articles.setdefault(int(label), []).append(article_id)
            cluster_to_probs.setdefault(int(label), []).append(float(prob))

        result = ReconcileResult()

        # Noise articles (-1)
        result.noise_article_ids = cluster_to_articles.pop(-1, [])

        for _cluster_label, members in cluster_to_articles.items():
            # What existing stories do these members belong to?
            story_to_members: dict[str, list[str]] = {}
            unassigned: list[str] = []
            for aid in members:
                sid = article_to_story.get(aid, "")
                if sid:
                    story_to_members.setdefault(sid, []).append(aid)
                else:
                    unassigned.append(aid)

            existing_stories = list(story_to_members.keys())

            if len(existing_stories) == 0:
                # All unassigned → new story
                if len(members) >= self.min_cluster_size:
                    result.new_stories.append(NewStoryOp(article_ids=members))

            elif len(existing_stories) == 1:
                # Absorb any unassigned members into the existing story
                if unassigned:
                    # Treat as a soft-merge (assign unassigned to existing story)
                    result.new_stories.append(NewStoryOp(article_ids=unassigned))

            else:
                # Multiple existing stories all fall into the same HDBSCAN cluster → MERGE
                target = max(existing_stories, key=lambda sid: story_article_counts.get(sid, 0))
                sources = [sid for sid in existing_stories if sid != target]
                
                # Check if it's borderline
                median_prob = float(np.median(cluster_to_probs[_cluster_label]))
                action = "merge"
                
                if median_prob < self.borderline_threshold and self.gateway is not None:
                    # Agentic adjudication
                    action, highlights, is_pattern = await self._run_agent(
                        f"Potential merge of stories. Target: {target}, Sources: {sources}", 
                        target, 
                        sources[0],
                    )
                    if is_pattern:
                        result.is_pattern[target] = True
                    if highlights:
                        result.timeline_highlights[target] = highlights
                
                if action == "merge":
                    for source in sources:
                        result.merges.append(
                            MergeOp(
                                target_story_id=target,
                                source_story_id=source,
                                article_ids=story_to_members[source],
                            )
                        )
                    # Absorb any unassigned members too
                    if unassigned:
                        result.new_stories.append(NewStoryOp(article_ids=unassigned))

        # Detect SPLITS: story that has articles in multiple HDBSCAN clusters
        story_cluster_map: dict[str, list[int]] = {}
        for label_int, members_in_cluster in {
            **cluster_to_articles,
            **{-1: result.noise_article_ids},
        }.items():
            for aid in members_in_cluster:
                sid = article_to_story.get(aid, "")
                if sid:
                    story_cluster_map.setdefault(sid, []).append(label_int)

        for story_id, cluster_labels_for_story in story_cluster_map.items():
            unique_labels = {lb for lb in cluster_labels_for_story if lb != -1}
            if len(unique_labels) > 1:
                # Story appears in multiple distinct clusters → split
                cluster_sizes = {lb: len(cluster_to_articles.get(lb, [])) for lb in unique_labels}
                keep_label = max(cluster_sizes, key=lambda lb: cluster_sizes[lb])
                
                # Check if the split cluster itself is borderline
                for split_label in unique_labels:
                    if split_label == keep_label:
                        continue
                    split_articles = [
                        aid
                        for aid in cluster_to_articles.get(split_label, [])
                        if article_to_story.get(aid, "") == story_id
                    ]
                    if split_articles:
                        median_prob = float(np.median(cluster_to_probs[split_label]))
                        action = "split"
                        
                        if median_prob < self.borderline_threshold and self.gateway is not None:
                            action, highlights, is_pattern = await self._run_agent(
                                f"Potential split of story {story_id}.", 
                                story_id, 
                                story_id,
                            )
                            if is_pattern:
                                result.is_pattern[story_id] = True
                            if highlights:
                                result.timeline_highlights[story_id] = highlights
                                
                        if action in ("split", "keep_separate") and action != "merge":
                            # 'keep_separate' for a split means separate them -> perform split
                            # 'split' means split
                            result.splits.append(
                                SplitOp(
                                    source_story_id=story_id,
                                    article_ids=split_articles,
                                )
                            )

        return result

    async def _run_agent(self, context: str, cluster_a: str, cluster_b: str) -> tuple[str, list[str], bool]:
        import structlog

        from app.application.use_cases.shared.agent_loop import (
            AgentDidNotConvergeError,
            AgentLoop,
        )
        from app.application.use_cases.shared.prompts.agentic_clustering import (
            SYSTEM_PROMPT,
            TOOL_NAMES,
            validate_final_answer,
        )
        
        logger = structlog.get_logger(__name__)

        loop = AgentLoop(
            gateway=self.gateway,
            system_prompt=SYSTEM_PROMPT,
            tool_names=TOOL_NAMES,
            tools=self.tools,
            max_iterations=6,
            max_tokens_per_step=600,
            agent_name="clustering_agent",
        )

        initial_msg = (
            f"{context}\n"
            f"Cluster A: {cluster_a}\n"
            f"Cluster B: {cluster_b}\n\n"
            "Analyze the content and determine if these represent the same event (merge) "
            "or distinct events (split / keep_separate)."
        )

        try:
            loop_result = await loop.run(initial_msg, run_id=f"clustering:{cluster_a}:{cluster_b}")
        except AgentDidNotConvergeError:
            logger.warning("clustering.agent_did_not_converge")
            return "merge", [], False  # fallback

        final = loop_result.final_step
        try:
            validate_final_answer(final)
        except ValueError as ve:
            logger.warning("clustering.invalid_final_answer", error=str(ve))
            return "merge", [], False

        return str(final["action"]), list(final.get("timeline_highlights", [])), bool(final.get("is_pattern", False))

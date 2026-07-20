"""Incremental story assignment use case.

For each newly embedded article:
  1. Load the article's embedding vector.
  2. Fetch the "active stories" shortlist from a Redis-cached set of
     (story_id, centroid_vector) pairs — avoiding a full pgvector scan on
     every single article.
  3. Compute cosine similarity against each candidate centroid.
  4. If best_similarity >= SIMILARITY_THRESHOLD → join that story; update
     its centroid as a running average; return the story_id.
  5. Otherwise → create a new story (with this article as the seed); set
     the centroid to the article's embedding.

Centroid update uses an online (running-average) formula:
  new_centroid = (old_centroid * n + new_vec) / (n + 1)
then L2-normalise so cosine comparisons stay consistent.

This module has no infrastructure imports — it depends only on
app.domain.interfaces.{repositories, services}.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

SIMILARITY_THRESHOLD = 0.75  # default; overridden via ClusteringSettings


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Return cosine similarity in [-1, 1] between two vectors."""
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def update_centroid(old_centroid: list[float], n: int, new_vec: list[float]) -> list[float]:
    """Return L2-normalised running-average centroid after adding *new_vec*.

    Parameters
    ----------
    old_centroid:
        Current centroid vector.
    n:
        Number of articles already in the cluster (BEFORE adding this one).
    new_vec:
        The new article's embedding (assumed L2-normalised).
    """
    raw = [(c * n + v) / (n + 1) for c, v in zip(old_centroid, new_vec, strict=True)]
    norm = math.sqrt(sum(x * x for x in raw))
    if norm == 0.0:
        return raw
    return [x / norm for x in raw]


@dataclass
class AssignmentResult:
    story_id: str
    created: bool  # True when a new story was spun up
    similarity: float  # 0.0 when created=True


class AssignToStory:
    """Incremental story assignment.

    Parameters
    ----------
    threshold:
        Minimum cosine similarity to join an existing story.
    """

    def __init__(self, threshold: float = SIMILARITY_THRESHOLD) -> None:
        self.threshold = threshold

    def assign(
        self,
        article_id: str,
        article_vec: list[float],
        active_stories: list[tuple[str, list[float], int]],
    ) -> AssignmentResult:
        """Determine which story *article_id* belongs to.

        Parameters
        ----------
        article_id:
            ID of the article being assigned (used only for logging; not mutated here).
        article_vec:
            L2-normalised embedding of the article.
        active_stories:
            List of (story_id, centroid_vector, member_count) for active stories.

        Returns
        -------
        AssignmentResult with the chosen story_id and whether it was created.
        """
        best_story_id: str | None = None
        best_sim = 0.0

        for story_id, centroid, _ in active_stories:
            sim = cosine_similarity(article_vec, centroid)
            if sim > best_sim:
                best_sim = sim
                best_story_id = story_id

        if best_story_id is not None and best_sim >= self.threshold:
            return AssignmentResult(
                story_id=best_story_id,
                created=False,
                similarity=best_sim,
            )

        # No match — caller is responsible for creating the story in DB
        return AssignmentResult(story_id="", created=True, similarity=0.0)

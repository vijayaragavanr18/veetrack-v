"""Shared data types for the feed API — Fast Path and Cold Path payloads.

These are pure dataclasses with no infrastructure imports.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Redis key helpers -------------------------------------------------------

_FEED_KEY_PREFIX = "vt:feed:"
_TRACKED_KEY_PREFIX = "vt:tracked:"

# Fast Path feed payload — 10 min TTL.
# Rationale: story risk levels and clusters update when the pipeline runs
# (typically every 15 min ingest + 5 min NLP pipeline).  At 10 min the
# worst-case staleness is one pipeline cycle; explicit invalidation on any
# story write makes the TTL a safety net, not the primary eviction trigger.
FEED_CACHE_TTL = 600

# Alias-resolve micro-cache — 60 s.
# The entity_aliases table grows via the ingestion pipeline but rarely changes
# for existing aliases.  A 60-second in-process TTL on the 1-row alias lookup
# (which runs on *every* Fast Path request) avoids repeated DB round-trips
# while staying fresh for newly created aliases.
ALIAS_CACHE_TTL = 60

# Cold-path result micro-cache — 30 s.
# First search for an unknown keyword falls through to pgvector + trigram.
# A 30 s shared cache prevents a thundering-herd on the first few seconds
# while the background entity-tracking task is spun up.
COLD_RESULT_CACHE_TTL = 30


def feed_cache_key(entity_id: str) -> str:
    return f"{_FEED_KEY_PREFIX}{entity_id}"


def tracked_key(entity_id: str) -> str:
    """Key whose presence means this entity is actively tracked (has pipeline output)."""
    return f"{_TRACKED_KEY_PREFIX}{entity_id}"


# Payload shapes ----------------------------------------------------------

@dataclass
class ArticleSummaryItem:
    id: str
    headline: str
    publisher: str
    published_at: str
    sentiment_label: str


@dataclass
class InsightItem:
    what_happened: str
    why_happened: str
    model_used: str


@dataclass
class RecommendationItem:
    id: str
    audience: str
    recommendation_text: str
    risk_level: str
    confidence_score: float
    needs_human_review: bool


@dataclass
class StoryPayload:
    """Full 4-page story payload cached by the build_feed_cache worker task."""

    id: str
    title: str
    status: str
    risk_level: str
    primary_entity_id: str
    entity_name: str
    article_count: int
    # Page 1 — Original articles
    articles: list[ArticleSummaryItem] = field(default_factory=list)
    # Page 2 — AI Insight
    insight: InsightItem | None = None
    # Page 3 — Cluster (member headlines, no raw embeddings)
    cluster_member_ids: list[str] = field(default_factory=list)
    # Page 4 — Recommendations (only approved ones in cached payload)
    recommendations: list[RecommendationItem] = field(default_factory=list)
    updated_at: str = ""


@dataclass
class FeedPage:
    """Cursor-paginated list of stories returned by GET /feed."""

    stories: list[StoryPayload]
    next_cursor: str | None
    entity_id: str
    entity_name: str
    path: str  # "fast" or "cold"

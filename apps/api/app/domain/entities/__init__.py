"""Domain entities — plain Python dataclasses with no framework dependencies."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

RiskLevel = Literal["low", "medium", "high", "critical"]
StoryStatus = Literal["active", "resolved", "archived"]
SentimentLabel = Literal["positive", "negative", "neutral", "mixed"]
EntityType = Literal["company", "person", "topic"]
RecommendationAudience = Literal["pr", "exec", "marketing"]
SourceType = Literal["newsdata", "twitter", "rss", "youtube"]
UserRole = Literal["owner", "admin", "analyst", "viewer"]


@dataclass
class Entity:
    """A canonical real-world entity resolved from raw text mentions."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    canonical_name: str = ""
    type: EntityType = "topic"
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass
class Article:
    """A single ingested news/social/RSS/YouTube article."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source_id: str = ""
    external_id: str = ""
    url: str = ""
    headline: str = ""
    hero_image_url: str | None = None
    publisher: str = ""
    published_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    clean_content: str = ""
    language: str = "en"
    sentiment_label: SentimentLabel = "neutral"
    sentiment_score: float = 0.0
    dedup_hash: str = ""
    ingested_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class Story:
    """A cluster of related articles grouped around a primary entity and theme."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    primary_entity_id: str = ""
    title: str = ""
    status: StoryStatus = "active"
    risk_level: RiskLevel = "low"
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class StoryInsight:
    """AI-generated executive summary for a story."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    story_id: str = ""
    what_happened: str = ""
    why_happened: str = ""
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    model_used: str = ""
    token_cost: int = 0


@dataclass
class StoryRecommendation:
    """A confidence-gated AI recommendation associated with a story."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    story_id: str = ""
    recommendation_text: str = ""
    audience: RecommendationAudience = "exec"
    risk_level: RiskLevel = "low"
    confidence_score: float = 0.0
    needs_human_review: bool = False
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class Workspace:
    """A multi-tenant workspace grouping users and their data."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    plan: str = "free"
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class User:
    """A workspace member with an RBAC role."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    workspace_id: str = ""
    email: str = ""
    role: UserRole = "viewer"
    hashed_password: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class Source:
    """An external data source (NewsData.io, RSS feed, Twitter, YouTube)."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    type: SourceType = "newsdata"
    config_json: dict[str, object] = field(default_factory=dict)
    is_active: bool = True
    rate_limit_budget: float = 1.0


@dataclass
class RawArticle:
    """Unnormalized article as received from a source connector.

    Persisted to the articles table with clean_content == raw_content.
    Normalization (Phase 11) will populate clean_content from raw_content.
    """

    external_id: str
    url: str
    headline: str
    publisher: str
    published_at: datetime
    raw_content: str
    language: str = "en"
    hero_image_url: str | None = None
    metadata_json: dict[str, object] = field(default_factory=dict)


@dataclass
class QuotaStatus:
    """Current rate-limit and circuit-breaker state for a source."""

    source_id: str
    calls_made: int
    quota_limit: int
    window_start: datetime
    circuit_open: bool = False
    circuit_open_until: datetime | None = None

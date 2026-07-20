"""BriefDocument — renderer-agnostic executive brief domain model.

Populated by BuildBrief use case; consumed by PDF and PPTX renderers.
No infrastructure or framework imports allowed in this file.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class BriefStoryItem:
    """One story entry inside a brief."""

    story_id: str
    title: str
    entity_name: str
    risk_level: str  # low / medium / high / critical
    sentiment_label: str
    article_count: int
    # Page-2 AI insight
    what_happened: str
    why_happened: str
    # Page-4 top recommendation (audience=exec, highest confidence)
    top_recommendation: str
    top_rec_confidence: float
    published_at: str  # ISO-8601 of most-recent article


@dataclass
class BriefDocument:
    """Renderer-agnostic executive brief payload."""

    workspace_id: str
    entity_keyword: str
    generated_at: datetime
    window_days: int
    stories: list[BriefStoryItem] = field(default_factory=list)
    # Optional summary line used as PDF/PPT subtitle
    subtitle: str = ""

"""BuildBrief use case — selects and ranks stories for an executive brief.

Pure application logic — no infrastructure imports.  The caller injects a
`DbQuery` callable so the use case can run SQL without importing SQLAlchemy.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.domain.entities.brief import BriefDocument, BriefStoryItem

# Type alias for the injected DB query callable (same pattern as GetFeed)
DbQuery = Callable[[str, dict[str, Any]], Awaitable[list[dict[str, Any]]]]

_RISK_ORDER = {"critical": 4, "high": 3, "medium": 2, "low": 1}


@dataclass
class BuildBriefInput:
    workspace_id: str
    entity_keyword: str
    window_days: int = 7
    max_stories: int = 10


class BuildBrief:
    """Select top N stories for a keyword + time window, ordered by risk then recency."""

    def __init__(self, db_query: DbQuery) -> None:
        self._db_query = db_query

    async def execute(self, inp: BuildBriefInput) -> BriefDocument:
        rows = await self._db_query(
            _STORIES_SQL,
            {
                "keyword": f"%{inp.entity_keyword}%",
                "window_days": inp.window_days,
                "limit": inp.max_stories * 3,  # fetch extra; rank in Python
            },
        )

        items = [_row_to_item(r) for r in rows]

        # Rank: risk desc, then most-recent article desc
        items.sort(
            key=lambda x: (
                _RISK_ORDER.get(x.risk_level, 0),
                x.published_at,
            ),
            reverse=True,
        )
        items = items[: inp.max_stories]

        risk_counts = {
            "critical": sum(1 for s in items if s.risk_level == "critical"),
            "high": sum(1 for s in items if s.risk_level == "high"),
        }
        subtitle_parts = []
        if risk_counts["critical"]:
            subtitle_parts.append(f"{risk_counts['critical']} critical")
        if risk_counts["high"]:
            subtitle_parts.append(f"{risk_counts['high']} high-risk")
        subtitle = (
            f"{', '.join(subtitle_parts)} {'story' if sum(risk_counts.values()) == 1 else 'stories'}"
            if subtitle_parts
            else f"{len(items)} stories"
        )

        return BriefDocument(
            workspace_id=inp.workspace_id,
            entity_keyword=inp.entity_keyword,
            generated_at=datetime.now(UTC),
            window_days=inp.window_days,
            stories=items,
            subtitle=subtitle,
        )


# ---------------------------------------------------------------------------
# SQL — stories for entity keyword, with best insight + top exec recommendation
# ---------------------------------------------------------------------------

_STORIES_SQL = """
SELECT
    s.id                        AS story_id,
    s.title,
    s.risk_level,
    s.updated_at,
    e.canonical_name            AS entity_name,
    COUNT(DISTINCT sa.article_id) AS article_count,
    -- most-recent article date in this cluster
    MAX(a.published_at)         AS latest_published_at,
    -- AI insight (latest)
    si.what_happened,
    si.why_happened,
    -- dominant sentiment from most-recent article
    (SELECT a2.sentiment_label
       FROM articles a2
       JOIN story_articles sa2 ON sa2.article_id = a2.id
      WHERE sa2.story_id = s.id
      ORDER BY a2.published_at DESC
      LIMIT 1)                  AS sentiment_label,
    -- top exec recommendation (highest confidence, approved only)
    (SELECT sr.recommendation_text
       FROM story_recommendations sr
      WHERE sr.story_id = s.id
        AND sr.audience = 'exec'
        AND sr.needs_human_review = FALSE
      ORDER BY sr.confidence_score DESC
      LIMIT 1)                  AS top_recommendation,
    (SELECT sr.confidence_score
       FROM story_recommendations sr
      WHERE sr.story_id = s.id
        AND sr.audience = 'exec'
        AND sr.needs_human_review = FALSE
      ORDER BY sr.confidence_score DESC
      LIMIT 1)                  AS top_rec_confidence
FROM stories s
JOIN entities e ON e.id = s.primary_entity_id
LEFT JOIN story_articles sa  ON sa.story_id = s.id
LEFT JOIN articles a         ON a.id = sa.article_id
LEFT JOIN story_insights si  ON si.story_id = s.id
WHERE
    s.status = 'active'
    AND (
        e.canonical_name ILIKE :keyword
        OR s.title       ILIKE :keyword
    )
    AND s.updated_at >= NOW() - INTERVAL '1 day' * :window_days
GROUP BY s.id, e.canonical_name, si.what_happened, si.why_happened
ORDER BY s.updated_at DESC
LIMIT :limit
"""


def _row_to_item(row: dict[str, Any]) -> BriefStoryItem:
    latest = row.get("latest_published_at")
    published_at = latest.isoformat() if hasattr(latest, "isoformat") else str(latest or "")
    return BriefStoryItem(
        story_id=str(row["story_id"]),
        title=str(row["title"] or ""),
        entity_name=str(row.get("entity_name") or ""),
        risk_level=str(row.get("risk_level") or "low"),
        sentiment_label=str(row.get("sentiment_label") or "neutral"),
        article_count=int(row.get("article_count") or 0),
        what_happened=str(row.get("what_happened") or ""),
        why_happened=str(row.get("why_happened") or ""),
        top_recommendation=str(row.get("top_recommendation") or ""),
        top_rec_confidence=float(row.get("top_rec_confidence") or 0.0),
        published_at=published_at,
    )

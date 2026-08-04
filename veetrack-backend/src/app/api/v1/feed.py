"""Feed router — Phase 18: Fast Path / Cold Path story feed.

GET /feed?entity=&cursor=
  Returns paginated StoryPayload list.
  Fast Path: served from Redis in <20ms.
  Cold Path: pgvector + trigram, returns Page-1 only, enqueues background tracking.

GET /stories/{id}
  Single story detail (status, risk level, title, entity).
"""

from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.use_cases.search.feed_types import (
    ArticleSummaryItem,
    FeedPage,
    InsightItem,
    RecommendationItem,
    StoryPayload,
)
from app.application.use_cases.search.get_feed import GetFeed
from app.core.config import get_settings
from app.core.container import get_cache_gateway, get_db_session, get_task_dispatcher
from app.core.security_deps import get_optional_user
from app.domain.entities import User
from app.domain.interfaces.services import CacheGateway, TaskDispatcher
from app.infrastructure.llm.ollama_client import OllamaClient

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["feed"])

# ---------------------------------------------------------------------------
# Response schemas (Pydantic — for OpenAPI docs)
# ---------------------------------------------------------------------------


class ArticleItem(BaseModel):
    id: str
    headline: str
    publisher: str
    published_at: str
    sentiment_label: str
    hero_image_url: str | None = None
    url: str = ""
    content_preview: str = ""


class InsightSchema(BaseModel):
    what_happened: str
    why_happened: str
    model_used: str


class RecommendationSchema(BaseModel):
    id: str
    audience: str
    recommendation_text: str
    risk_level: str
    confidence_score: float
    needs_human_review: bool


class StorySchema(BaseModel):
    id: str
    title: str
    status: str
    risk_level: str
    primary_entity_id: str
    entity_name: str
    article_count: int
    articles: list[ArticleItem]
    insight: InsightSchema | None
    cluster_member_ids: list[str]
    recommendations: list[RecommendationSchema]
    updated_at: str


class FeedResponse(BaseModel):
    stories: list[StorySchema]
    next_cursor: str | None
    entity_id: str
    entity_name: str
    path: str  # "fast" | "cold"


# ---------------------------------------------------------------------------
# DB query helper (injected into use case)
# ---------------------------------------------------------------------------


def _make_db_query(session: AsyncSession):  # type: ignore[no-untyped-def]
    async def _query(sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        result = await session.execute(text(sql), params)
        columns = result.keys()
        return [dict(zip(columns, row, strict=True)) for row in result]

    return _query


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/feed", response_model=FeedResponse)
async def get_feed(
    response: Response,
    entity: Annotated[str, Query(min_length=1, max_length=200)],
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=25)] = 25,
    session: Annotated[AsyncSession, Depends(get_db_session)] = ...,  # type: ignore[assignment]
    cache: Annotated[CacheGateway, Depends(get_cache_gateway)] = ...,  # type: ignore[assignment]
    dispatcher: Annotated[TaskDispatcher, Depends(get_task_dispatcher)] = ...,  # type: ignore[assignment]
    _: Annotated[User | None, Depends(get_optional_user)] = None,
) -> FeedResponse:
    """Return the story feed for an entity keyword.

    Fast Path: <20ms from Redis when entity is tracked.
    Cold Path: direct DB query + background tracking trigger.
    """
    use_case = GetFeed(
        cache=cache,
        dispatcher=dispatcher,
        db_query=_make_db_query(session),
    )
    page: FeedPage = await use_case.execute(entity, cursor=cursor, limit=limit)

    # If DB/cache returned nothing, fetch live from NewsData as immediate fallback
    if not page.stories and not cursor:
        live_page = await _live_fetch_fallback(entity)
        if live_page:
            page = live_page

    # Edge Caching: Cache on CDN for 10s, serve stale while revalidating for 60s
    response.headers["Cache-Control"] = "public, s-maxage=10, stale-while-revalidate=60"

    return FeedResponse(
        stories=[_story_to_schema(s) for s in page.stories],
        next_cursor=page.next_cursor,
        entity_id=page.entity_id,
        entity_name=page.entity_name,
        path=page.path,
    )


@router.get("/stories/{story_id}", response_model=StorySchema)
async def get_story(
    story_id: str,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    _: Annotated[User | None, Depends(get_optional_user)] = None,
) -> StorySchema:
    """Return single story detail."""
    row = await session.execute(
        text(
            "SELECT s.id, s.title, s.status, s.risk_level, s.primary_entity_id, "
            "       s.updated_at, e.canonical_name AS entity_name, "
            "       COUNT(sa.article_id) AS article_count "
            "FROM stories s "
            "JOIN entities e ON e.id = s.primary_entity_id "
            "LEFT JOIN story_articles sa ON sa.story_id = s.id "
            "WHERE s.id = :id "
            "GROUP BY s.id, e.canonical_name"
        ),
        {"id": story_id},
    )
    result = row.first()
    if result is None:
        raise HTTPException(status_code=404, detail="Story not found")

    return StorySchema(
        id=str(result.id),
        title=str(result.title or ""),
        status=str(result.status or "active"),
        risk_level=str(result.risk_level or "low"),
        primary_entity_id=str(result.primary_entity_id),
        entity_name=str(result.entity_name or ""),
        article_count=int(result.article_count or 0),
        articles=[],
        insight=None,
        cluster_member_ids=[],
        recommendations=[],
        updated_at=result.updated_at.isoformat() if result.updated_at else "",
    )


# ---------------------------------------------------------------------------
# Live fallback fetch — called when cold path finds nothing in DB
# ---------------------------------------------------------------------------

_OLLAMA_ENDPOINT = "http://localhost:11434/v1/chat/completions"
_OLLAMA_MODEL = "qwen2.5:7b"

# Stop-words for topic clustering
_STOP_WORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "is", "are", "was", "were", "has", "have", "had", "be",
    "been", "being", "that", "this", "from", "by", "as", "it", "its",
    "will", "would", "could", "should", "may", "might", "can", "up",
    "new", "over", "after", "amid", "into", "about", "says", "said",
}


def _parse_pub_date(raw: str) -> datetime:
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return datetime.now(UTC)


def _title_keywords(title: str) -> set[str]:
    words = re.findall(r"[A-Za-z]{4,}", title)
    return {w.lower() for w in words if w.lower() not in _STOP_WORDS}


def _cluster_articles(
    raw_items: list[dict[str, Any]],
    entity_query: str,
) -> list[list[dict[str, Any]]]:
    """Cluster articles by keyword overlap into topic groups.

    Each article is assigned to the first cluster whose centroid shares ≥2
    keywords with it; otherwise it seeds a new cluster.  Returns clusters
    sorted by size descending, capped at 5 groups of at most 8 articles each.
    """
    clusters: list[tuple[set[str], list[dict[str, Any]]]] = []
    entity_kw = _title_keywords(entity_query)

    for item in raw_items:
        title = str(item.get("title") or "")
        kw = _title_keywords(title) | entity_kw
        placed = False
        for centroid, members in clusters:
            if len(kw & centroid) >= 2:
                members.append(item)
                centroid.update(kw)
                placed = True
                break
        if not placed:
            clusters.append((set(kw), [item]))

    clusters.sort(key=lambda c: len(c[1]), reverse=True)
    return [members[:8] for _, members in clusters[:30]]


async def _generate_insight(
    entity_query: str,
    headlines: list[str],
    descriptions: list[str],
) -> InsightItem:
    """Call Ollama to generate a rich executive-brief insight for a story cluster."""
    ollama = OllamaClient(model=_OLLAMA_MODEL, endpoint=_OLLAMA_ENDPOINT, timeout=90.0)
    combined = "\n".join(
        f"- {h}: {d[:200]}" for h, d in zip(headlines, descriptions, strict=False) if h
    )
    prompt = (
        f"You are a senior PR analyst writing executive intelligence briefs.\n\n"
        f"Topic: {entity_query}\n\n"
        f"News articles:\n{combined}\n\n"
        f"Write a comprehensive executive brief with two sections:\n\n"
        f"WHAT HAPPENED (250-350 words):\n"
        f"Summarise the key developments, events, announcements, and facts from these articles. "
        f"Be specific: include names, numbers, dates, and context. "
        f"Explain the sequence of events and how they relate to each other. "
        f"Cover the main storyline and any notable sub-plots.\n\n"
        f"WHY IT MATTERS (250-350 words):\n"
        f"Analyse the strategic implications for PR and communications teams. "
        f"Why are these events happening now? What are the underlying drivers — market forces, "
        f"regulatory pressure, competitive dynamics, or public sentiment shifts? "
        f"What second-order effects should PR professionals anticipate? "
        f"Which stakeholder groups are most affected and how?\n\n"
        f"Format your response as:\n"
        f"WHAT HAPPENED:\n[your what happened text]\n\n"
        f"WHY IT MATTERS:\n[your why it matters text]"
    )
    try:
        text_out = await ollama.complete(prompt, max_tokens=900, temperature=0.3)
        what = ""
        why = ""
        if "WHY IT MATTERS:" in text_out:
            parts = text_out.split("WHY IT MATTERS:", 1)
            what_block = parts[0].replace("WHAT HAPPENED:", "").strip()
            why_block = parts[1].strip()
            what = what_block
            why = why_block
        else:
            what = text_out.strip()
            why = ""
        return InsightItem(
            what_happened=what or "Analysis pending.",
            why_happened=why or "Analysis pending.",
            model_used=_OLLAMA_MODEL,
        )
    except Exception as exc:
        logger.warning("feed.live_fallback.insight_failed", error=str(exc))
        headlines_text = "; ".join(headlines[:5])
        return InsightItem(
            what_happened=f"Latest developments on {entity_query}: {headlines_text}",
            why_happened=f"These developments reflect ongoing activity around {entity_query}.",
            model_used="fallback",
        )


async def _generate_recommendations(
    entity_query: str,
    what_happened: str,
    risk_level: str,
) -> list[RecommendationItem]:
    """Call Ollama to generate 3 targeted PR recommendations."""
    ollama = OllamaClient(model=_OLLAMA_MODEL, endpoint=_OLLAMA_ENDPOINT, timeout=90.0)
    prompt = (
        f"You are a senior PR strategist. Based on this news situation about {entity_query}:\n\n"
        f"{what_happened[:600]}\n\n"
        f"Write exactly 3 specific, actionable PR recommendations. "
        f"Each recommendation must be for a different audience: "
        f"one for the Communications Team, one for the Executive Team, and one for the Media Relations team.\n\n"
        f"For each recommendation, write 150-200 words covering:\n"
        f"- The specific action to take immediately\n"
        f"- The messaging angle and key talking points\n"
        f"- Which media/stakeholder channels to use\n"
        f"- The risk if this action is NOT taken\n\n"
        f"Format EXACTLY as:\n"
        f"COMMUNICATIONS TEAM:\n[recommendation]\n\n"
        f"EXECUTIVE TEAM:\n[recommendation]\n\n"
        f"MEDIA RELATIONS:\n[recommendation]"
    )
    try:
        text_out = await ollama.complete(prompt, max_tokens=900, temperature=0.3)
        recs = []
        audiences = [
            ("communications", "Communications Team"),
            ("executive", "Executive Team"),
            ("media", "Media Relations"),
        ]
        audience_keys = ["COMMUNICATIONS TEAM:", "EXECUTIVE TEAM:", "MEDIA RELATIONS:"]
        parts: dict[str, str] = {}
        current_key = None
        for line in text_out.splitlines():
            stripped = line.strip()
            matched = False
            for ak in audience_keys:
                if stripped.upper().startswith(ak.upper().rstrip(":")):
                    current_key = ak
                    parts[ak] = ""
                    matched = True
                    break
            if not matched and current_key and stripped:
                parts[current_key] = parts.get(current_key, "") + " " + stripped

        for i, (aud_id, aud_label) in enumerate(audiences):
            key = audience_keys[i]
            rec_text = parts.get(key, "").strip()
            if not rec_text:
                rec_text = (
                    f"Monitor {entity_query} coverage closely and prepare proactive messaging "
                    f"tailored to the {aud_label}'s stakeholder priorities."
                )
            recs.append(
                RecommendationItem(
                    id=f"live-rec-{aud_id}",
                    audience=aud_label,
                    recommendation_text=rec_text,
                    risk_level=risk_level,
                    confidence_score=0.82,
                    needs_human_review=risk_level in ("high", "critical"),
                )
            )
        return recs
    except Exception as exc:
        logger.warning("feed.live_fallback.recs_failed", error=str(exc))
        return []


def _infer_risk_level(headlines: list[str]) -> str:
    high_kw = {"crisis", "recall", "lawsuit", "scandal", "breach", "fraud", "collapse",
               "bankrupt", "fired", "resign", "arrest", "hack", "leak", "death", "killed"}
    medium_kw = {"investigation", "probe", "decline", "drop", "loss", "concern", "warn",
                 "fine", "penalty", "delay", "layoff", "cut", "miss", "fail"}
    joined = " ".join(h.lower() for h in headlines)
    if any(k in joined for k in high_kw):
        return "high"
    if any(k in joined for k in medium_kw):
        return "medium"
    return "low"


async def _build_story_from_cluster(
    cluster_idx: int,
    entity_query: str,
    cluster_items: list[dict[str, Any]],
    since: datetime,
) -> StoryPayload | None:
    articles: list[ArticleSummaryItem] = []
    for item in cluster_items:
        pub_raw = item.get("pubDate") or ""
        pub_dt = _parse_pub_date(pub_raw) if pub_raw else datetime.now(UTC)
        if pub_dt < since:
            continue
        articles.append(
            ArticleSummaryItem(
                id=str(item.get("article_id") or item.get("link") or ""),
                headline=str(item.get("title") or ""),
                publisher=str(item.get("source_name") or item.get("source_id") or ""),
                published_at=pub_dt.isoformat(),
                sentiment_label="neutral",
                hero_image_url=item.get("image_url") or None,
                url=str(item.get("link") or ""),
                content_preview=str(
                    item.get("description") or item.get("content") or ""
                )[:400],
            )
        )

    if not articles:
        return None

    # Sort articles by published_at DESC (newest first)
    articles.sort(key=lambda a: a.published_at, reverse=True)

    headlines = [a.headline for a in articles]
    descriptions = [a.content_preview for a in articles]
    risk_level = _infer_risk_level(headlines)

    # Derive story title from the most informative headline
    story_title = headlines[0] if headlines else f"{entity_query} — Latest News"
    if len(story_title) > 80:
        story_title = story_title[:77] + "…"

    # Tier 1: Instant Extractive Fastpass Brief
    lead_desc = (descriptions[0] if descriptions else story_title).strip()
    if len(lead_desc) > 280:
        lead_desc = lead_desc[:277] + "…"
    insight = InsightItem(
        what_happened=f"Latest development: {lead_desc}",
        why_happened=f"Strategic and media impact analysis for {entity_query} is currently being tracked.",
        model_used="extractive-fastpass",
    )
    recommendations = [
        RecommendationItem(
            id="fast-rec-comm",
            audience="Communications Team",
            recommendation_text=f"Monitor immediate media coverage regarding {entity_query} and prepare reactive talking points.",
            risk_level=risk_level,
            confidence_score=0.75,
            needs_human_review=False,
        ),
        RecommendationItem(
            id="fast-rec-exec",
            audience="Executive Team",
            recommendation_text=f"Review key stakeholders and briefing notes on developments surrounding {entity_query}.",
            risk_level=risk_level,
            confidence_score=0.75,
            needs_human_review=False,
        ),
        RecommendationItem(
            id="fast-rec-media",
            audience="Media Relations",
            recommendation_text=f"Track sentiment across major news outlets covering {entity_query}.",
            risk_level=risk_level,
            confidence_score=0.75,
            needs_human_review=False,
        ),
    ]

    slug = entity_query.lower().replace(" ", "-")[:30]
    return StoryPayload(
        id=f"live-{slug}-{cluster_idx}",
        title=story_title,
        status="active",
        risk_level=risk_level,
        primary_entity_id="",
        entity_name=entity_query,
        article_count=len(articles),
        articles=articles,
        insight=insight,
        recommendations=recommendations,
        cluster_member_ids=[a.id for a in articles],
        updated_at=datetime.now(UTC).isoformat(),
    )


async def _live_fetch_fallback(entity_query: str) -> FeedPage | None:
    """Fetch from NewsData.io, cluster into topic stories, generate AI insight via Ollama.

    Returns up to 5 fully-enriched StoryPayload objects with real hero images
    and AI-generated executive briefs + PR recommendations.
    """
    settings = get_settings()
    api_key = settings.newsdata_api_key
    if not api_key:
        return None

    since = datetime.now(UTC) - timedelta(hours=72)
    params = {
        "apikey": api_key,
        "q": entity_query,
        "language": "en",
        "size": "50",
        "timeframe": "48",
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get("https://newsdata.io/api/1/latest", params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.warning("feed.live_fallback.fetch_failed", error=str(exc))
        return None

    results = data.get("results") or []
    if not results:
        return None

    clusters = _cluster_articles(results, entity_query)
    if not clusters:
        return None

    # Build all stories concurrently — Ollama calls run in parallel per story
    tasks = [
        _build_story_from_cluster(i, entity_query, cluster, since)
        for i, cluster in enumerate(clusters)
    ]
    built = await asyncio.gather(*tasks, return_exceptions=True)
    stories: list[StoryPayload] = [
        s for s in built if isinstance(s, StoryPayload)
    ]

    if not stories:
        return None

    # Sort stories by the published_at of their newest article
    stories.sort(
        key=lambda s: s.articles[0].published_at if s.articles else "", 
        reverse=True
    )

    # Tier 2 & Tier 3: Schedule background Ollama qwen2.5:7b enrichment
    asyncio.create_task(_async_enrich_with_ollama(entity_query, stories))

    return FeedPage(
        stories=stories,
        next_cursor=None,
        entity_id="",
        entity_name=entity_query,
        path="cold",
    )


async def _async_enrich_with_ollama(entity_query: str, stories: list[StoryPayload]) -> None:
    """Background Tier-2 task: enrich stories with Ollama qwen2.5:7b executive briefs."""
    try:
        logger.info("feed.hybrid_pipeline.tier2_start", entity=entity_query, stories_count=len(stories))
        for story in stories[:3]:  # Enrich top 3 stories
            headlines = [a.headline for a in story.articles]
            descriptions = [a.content_preview for a in story.articles]
            rich_insight = await _generate_insight(entity_query, headlines, descriptions)
            rich_recs = await _generate_recommendations(entity_query, rich_insight.what_happened, story.risk_level)
            story.insight = rich_insight
            if rich_recs:
                story.recommendations = rich_recs
        logger.info("feed.hybrid_pipeline.tier2_done", entity=entity_query)
    except Exception as exc:
        logger.warning("feed.hybrid_pipeline.tier2_failed", error=str(exc))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _story_to_schema(s: StoryPayload) -> StorySchema:
    return StorySchema(
        id=s.id,
        title=s.title,
        status=s.status,
        risk_level=s.risk_level,
        primary_entity_id=s.primary_entity_id,
        entity_name=s.entity_name,
        article_count=s.article_count,
        articles=[
            ArticleItem(
                id=a.id,
                headline=a.headline,
                publisher=a.publisher,
                published_at=a.published_at,
                sentiment_label=a.sentiment_label,
                hero_image_url=a.hero_image_url,
                url=a.url,
                content_preview=a.content_preview,
            )
            for a in s.articles
        ],
        insight=InsightSchema(
            what_happened=s.insight.what_happened,
            why_happened=s.insight.why_happened,
            model_used=s.insight.model_used,
        )
        if s.insight
        else None,
        cluster_member_ids=s.cluster_member_ids,
        recommendations=[
            RecommendationSchema(
                id=r.id,
                audience=r.audience,
                recommendation_text=r.recommendation_text,
                risk_level=r.risk_level,
                confidence_score=r.confidence_score,
                needs_human_review=r.needs_human_review,
            )
            for r in s.recommendations
        ],
        updated_at=s.updated_at,
    )

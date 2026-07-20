"""Unit tests for BuildBrief use case — selection and ranking logic."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.application.use_cases.exports.build_brief import BuildBrief, BuildBriefInput
from app.domain.entities.brief import BriefDocument, BriefStoryItem


# ---------------------------------------------------------------------------
# Fake DB query helper
# ---------------------------------------------------------------------------


def _make_row(
    story_id: str,
    title: str,
    risk_level: str = "low",
    updated_at: datetime | None = None,
    what_happened: str = "Something happened.",
    why_happened: str = "Because reasons.",
    top_recommendation: str = "Consider monitoring.",
    top_rec_confidence: float = 0.85,
    entity_name: str = "Tesla",
    article_count: int = 3,
    latest_published_at: datetime | None = None,
    sentiment_label: str = "neutral",
) -> dict:
    now = datetime.now(UTC)
    return {
        "story_id": story_id,
        "title": title,
        "risk_level": risk_level,
        "updated_at": updated_at or now,
        "entity_name": entity_name,
        "article_count": article_count,
        "latest_published_at": latest_published_at or now,
        "what_happened": what_happened,
        "why_happened": why_happened,
        "sentiment_label": sentiment_label,
        "top_recommendation": top_recommendation,
        "top_rec_confidence": top_rec_confidence,
    }


def make_db_query(rows: list[dict]):
    async def _query(sql: str, params: dict) -> list[dict]:
        return rows
    return _query


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_brief_empty_db_returns_empty_document() -> None:
    uc = BuildBrief(db_query=make_db_query([]))
    doc = await uc.execute(BuildBriefInput("ws1", "Tesla"))
    assert isinstance(doc, BriefDocument)
    assert doc.stories == []
    assert doc.entity_keyword == "Tesla"


@pytest.mark.asyncio
async def test_build_brief_returns_story_items() -> None:
    rows = [_make_row("s1", "Tesla probe"), _make_row("s2", "Tesla earnings")]
    uc = BuildBrief(db_query=make_db_query(rows))
    doc = await uc.execute(BuildBriefInput("ws1", "Tesla"))
    assert len(doc.stories) == 2
    titles = {s.title for s in doc.stories}
    assert "Tesla probe" in titles
    assert "Tesla earnings" in titles


@pytest.mark.asyncio
async def test_build_brief_ranks_critical_above_low() -> None:
    now = datetime.now(UTC)
    rows = [
        _make_row("s-low", "Low story", risk_level="low", updated_at=now),
        _make_row("s-crit", "Critical story", risk_level="critical", updated_at=now - timedelta(hours=1)),
    ]
    uc = BuildBrief(db_query=make_db_query(rows))
    doc = await uc.execute(BuildBriefInput("ws1", "Tesla"))
    assert doc.stories[0].risk_level == "critical"


@pytest.mark.asyncio
async def test_build_brief_ranks_high_above_medium() -> None:
    now = datetime.now(UTC)
    rows = [
        _make_row("s-med", "Medium", risk_level="medium", updated_at=now),
        _make_row("s-hi", "High", risk_level="high", updated_at=now - timedelta(hours=2)),
    ]
    uc = BuildBrief(db_query=make_db_query(rows))
    doc = await uc.execute(BuildBriefInput("ws1", "Tesla"))
    assert doc.stories[0].risk_level == "high"


@pytest.mark.asyncio
async def test_build_brief_respects_max_stories() -> None:
    rows = [_make_row(f"s{i}", f"Story {i}") for i in range(20)]
    uc = BuildBrief(db_query=make_db_query(rows))
    doc = await uc.execute(BuildBriefInput("ws1", "Tesla", max_stories=5))
    assert len(doc.stories) <= 5


@pytest.mark.asyncio
async def test_build_brief_subtitle_reflects_risk_counts() -> None:
    rows = [
        _make_row("s1", "T1", risk_level="critical"),
        _make_row("s2", "T2", risk_level="high"),
        _make_row("s3", "T3", risk_level="low"),
    ]
    uc = BuildBrief(db_query=make_db_query(rows))
    doc = await uc.execute(BuildBriefInput("ws1", "Tesla"))
    assert "critical" in doc.subtitle
    assert "high" in doc.subtitle


@pytest.mark.asyncio
async def test_build_brief_subtitle_generic_when_all_low() -> None:
    rows = [_make_row("s1", "T1", risk_level="low"), _make_row("s2", "T2", risk_level="medium")]
    uc = BuildBrief(db_query=make_db_query(rows))
    doc = await uc.execute(BuildBriefInput("ws1", "Tesla"))
    assert "stories" in doc.subtitle or "story" in doc.subtitle


@pytest.mark.asyncio
async def test_build_brief_story_item_fields() -> None:
    now = datetime.now(UTC)
    rows = [
        _make_row(
            "s1",
            "Test story",
            risk_level="high",
            what_happened="X happened",
            why_happened="Y reason",
            top_recommendation="Consider Z",
            top_rec_confidence=0.9,
            entity_name="Apple",
            article_count=5,
            latest_published_at=now,
        )
    ]
    uc = BuildBrief(db_query=make_db_query(rows))
    doc = await uc.execute(BuildBriefInput("ws1", "Apple"))
    s = doc.stories[0]
    assert s.what_happened == "X happened"
    assert s.why_happened == "Y reason"
    assert s.top_recommendation == "Consider Z"
    assert s.top_rec_confidence == 0.9
    assert s.entity_name == "Apple"
    assert s.article_count == 5


@pytest.mark.asyncio
async def test_build_brief_handles_null_insight_gracefully() -> None:
    rows = [_make_row("s1", "No insight", what_happened="", why_happened="")]
    uc = BuildBrief(db_query=make_db_query(rows))
    doc = await uc.execute(BuildBriefInput("ws1", "Tesla"))
    assert doc.stories[0].what_happened == ""


@pytest.mark.asyncio
async def test_build_brief_handles_null_recommendation_gracefully() -> None:
    rows = [_make_row("s1", "No rec", top_recommendation="", top_rec_confidence=0.0)]
    uc = BuildBrief(db_query=make_db_query(rows))
    doc = await uc.execute(BuildBriefInput("ws1", "Tesla"))
    assert doc.stories[0].top_recommendation == ""


@pytest.mark.asyncio
async def test_build_brief_window_days_passed_to_query() -> None:
    captured_params: list[dict] = []

    async def _query(sql: str, params: dict) -> list[dict]:
        captured_params.append(params)
        return []

    uc = BuildBrief(db_query=_query)
    await uc.execute(BuildBriefInput("ws1", "Tesla", window_days=14))
    assert captured_params[0]["window_days"] == 14


@pytest.mark.asyncio
async def test_build_brief_keyword_passed_to_query() -> None:
    captured_params: list[dict] = []

    async def _query(sql: str, params: dict) -> list[dict]:
        captured_params.append(params)
        return []

    uc = BuildBrief(db_query=_query)
    await uc.execute(BuildBriefInput("ws1", "Apple"))
    assert "Apple" in captured_params[0]["keyword"]

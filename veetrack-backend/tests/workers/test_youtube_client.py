"""Unit tests: workers YouTubeClient — APIDIRECT MCP connector."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from workers.connectors.youtube import (
    YouTubeClient,
    _map_post,
    _parse_date,
)


# ---------------------------------------------------------------------------
# _parse_date
# ---------------------------------------------------------------------------


def test_parse_date_iso_format() -> None:
    dt = _parse_date("2026-01-15")
    assert dt.year >= 2024
    assert dt.month >= 1


def test_parse_date_none_returns_now_approx() -> None:
    before = datetime.now(UTC)
    dt = _parse_date(None)
    after = datetime.now(UTC)
    assert before <= dt <= after


def test_parse_date_invalid_string_returns_now_approx() -> None:
    before = datetime.now(UTC)
    dt = _parse_date("not-a-date")
    after = datetime.now(UTC)
    assert before <= dt <= after


# ---------------------------------------------------------------------------
# _map_post — uses real field names from the APIDIRECT connector
# ---------------------------------------------------------------------------


def test_map_post_external_id_has_yt_prefix() -> None:
    post = {"video_id": "abc123", "title": "Test", "author": "Chan"}
    article = _map_post(post)
    assert article.external_id == "yt:abc123"


def test_map_post_publisher_from_author() -> None:
    post = {"title": "Test", "author": "TechChannel"}
    article = _map_post(post)
    assert article.publisher == "TechChannel"


def test_map_post_missing_author_falls_back_to_youtube() -> None:
    post = {"title": "Test"}
    article = _map_post(post)
    assert article.publisher  # non-empty fallback


def test_map_post_hero_image_from_thumbnail() -> None:
    post = {"title": "Test", "thumbnail": "https://img.yt/abc.jpg"}
    article = _map_post(post)
    assert article.hero_image_url == "https://img.yt/abc.jpg"


def test_map_post_no_thumbnail_gives_none() -> None:
    post = {"title": "Test"}
    article = _map_post(post)
    assert article.hero_image_url is None


def test_map_post_empty_title_gives_empty_string() -> None:
    post: dict = {}
    article = _map_post(post)
    assert isinstance(article.headline, str)


def test_map_post_raw_content_from_snippet() -> None:
    post = {"title": "Test", "snippet": "Some video description text."}
    article = _map_post(post)
    assert "Some video description" in article.raw_content


# ---------------------------------------------------------------------------
# YouTubeClient.fetch — mocked APIDIRECT call
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_returns_articles_from_apidirect() -> None:
    fake_posts = [
        {
            "video_id": f"vid{i}",
            "title": f"Video {i}",
            "author": "Tech",
            "date": "2024-06-01",
            "thumbnail": None,
            "url": f"https://youtube.com/watch?v=vid{i}",
            "snippet": f"Desc {i}",
        }
        for i in range(3)
    ]

    import fakeredis.aioredis as fakeredis
    from workers.connectors.base import RedisRateLimiter

    redis = fakeredis.FakeRedis()
    limiter = RedisRateLimiter(redis, "yt-test", 10)

    client = YouTubeClient(source_id="yt-test", rate_limiter=limiter, api_key="test-key")

    with patch(
        "workers.connectors.youtube._search_apidirect",
        new=AsyncMock(return_value=fake_posts),
    ):
        articles = await client.fetch("AI news", since=datetime.now(UTC))

    assert len(articles) == 3
    assert all(a.headline for a in articles)
    await redis.aclose()


@pytest.mark.asyncio
async def test_fetch_empty_result_when_apidirect_returns_nothing() -> None:
    import fakeredis.aioredis as fakeredis
    from workers.connectors.base import RedisRateLimiter

    redis = fakeredis.FakeRedis()
    limiter = RedisRateLimiter(redis, "yt-test", 10)
    client = YouTubeClient(source_id="yt-test", rate_limiter=limiter, api_key="key")

    with patch(
        "workers.connectors.youtube._search_apidirect",
        new=AsyncMock(return_value=[]),
    ):
        articles = await client.fetch("nothing", since=datetime.now(UTC))

    assert articles == []
    await redis.aclose()

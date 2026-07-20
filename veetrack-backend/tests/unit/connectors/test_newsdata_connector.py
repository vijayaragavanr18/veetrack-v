"""Unit tests: NewsDataConnector response mapping + HTTP behaviour (respx mocks)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import fakeredis.aioredis as fakeredis
import httpx
import pytest
import respx

from app.infrastructure.connectors.base import RedisRateLimiter
from app.infrastructure.connectors.newsdata_connector import (
    NewsDataConnector,
    _map_article,
    _parse_published_at,
)

SOURCE_ID = "nd-test"
SINCE = datetime.now(UTC) - timedelta(hours=1)


@pytest.fixture()
async def redis() -> fakeredis.FakeRedis:
    return fakeredis.FakeRedis(decode_responses=False)


@pytest.fixture()
def limiter(redis: fakeredis.FakeRedis) -> RedisRateLimiter:
    return RedisRateLimiter(redis, SOURCE_ID, calls_per_minute=100)


@pytest.fixture()
def connector(limiter: RedisRateLimiter) -> NewsDataConnector:
    return NewsDataConnector(
        api_key="test-key",
        source_id=SOURCE_ID,
        rate_limiter=limiter,
    )


# ---------------------------------------------------------------------------
# _parse_published_at
# ---------------------------------------------------------------------------

def test_parse_published_at_valid() -> None:
    dt = _parse_published_at("2024-12-10 09:15:30")
    assert dt.year == 2024
    assert dt.month == 12
    assert dt.tzinfo is not None


def test_parse_published_at_none_returns_now() -> None:
    dt = _parse_published_at(None)
    assert (datetime.now(UTC) - dt).total_seconds() < 5


def test_parse_published_at_bad_format_returns_now() -> None:
    dt = _parse_published_at("not-a-date")
    assert (datetime.now(UTC) - dt).total_seconds() < 5


# ---------------------------------------------------------------------------
# _map_article
# ---------------------------------------------------------------------------

def test_map_article_full_response() -> None:
    item = {
        "article_id": "abc123",
        "link": "https://example.com/story",
        "title": "Tesla Recall",
        "source_name": "Reuters",
        "pubDate": "2024-12-10 09:15:00",
        "content": "Full article text here.",
        "language": "en",
        "image_url": "https://img.example.com/photo.jpg",
    }
    article = _map_article(item, SOURCE_ID)
    assert article is not None
    assert article.headline == "Tesla Recall"
    assert article.publisher == "Reuters"
    assert article.hero_image_url == "https://img.example.com/photo.jpg"
    assert article.raw_content == "Full article text here."
    assert article.language == "en"


def test_map_article_missing_title_returns_none() -> None:
    item = {"article_id": "x", "link": "https://example.com"}
    assert _map_article(item, SOURCE_ID) is None


def test_map_article_missing_url_returns_none() -> None:
    item = {"article_id": "x", "title": "Something"}
    assert _map_article(item, SOURCE_ID) is None


def test_map_article_falls_back_to_description() -> None:
    item = {
        "article_id": "y",
        "link": "https://example.com",
        "title": "Headline",
        "description": "Short desc",
    }
    article = _map_article(item, SOURCE_ID)
    assert article is not None
    assert article.raw_content == "Short desc"


def test_map_article_no_image_is_none() -> None:
    item = {
        "article_id": "z",
        "link": "https://example.com",
        "title": "Headline",
    }
    article = _map_article(item, SOURCE_ID)
    assert article is not None
    assert article.hero_image_url is None


# ---------------------------------------------------------------------------
# NewsDataConnector.fetch — HTTP mocked with respx
# ---------------------------------------------------------------------------

_GOOD_RESPONSE = {
    "status": "success",
    "totalResults": 1,
    "results": [
        {
            "article_id": "art-001",
            "link": "https://newsdata.io/article/1",
            "title": "Tesla Autopilot Update",
            "source_name": "TechCrunch",
            "pubDate": "2024-12-10 10:00:00",
            "content": "Article body text.",
            "language": "en",
            "image_url": None,
        }
    ],
}


@pytest.mark.asyncio
@respx.mock
async def test_fetch_success(connector: NewsDataConnector) -> None:
    respx.get("https://newsdata.io/api/1/news/search").mock(
        return_value=httpx.Response(200, json=_GOOD_RESPONSE)
    )
    articles = await connector.fetch("Tesla", SINCE)
    assert len(articles) == 1
    assert articles[0].headline == "Tesla Autopilot Update"
    assert articles[0].external_id == "art-001"


@pytest.mark.asyncio
@respx.mock
async def test_fetch_skips_invalid_items(connector: NewsDataConnector) -> None:
    bad_response = {
        "status": "success",
        "results": [
            {"article_id": "ok", "link": "https://example.com", "title": "Valid"},
            {"article_id": "no-url", "title": "Missing URL"},   # invalid
            {"link": "https://example.com"},                     # no title
        ],
    }
    respx.get("https://newsdata.io/api/1/news/search").mock(
        return_value=httpx.Response(200, json=bad_response)
    )
    articles = await connector.fetch("test", SINCE)
    assert len(articles) == 1


@pytest.mark.asyncio
@respx.mock
async def test_fetch_401_raises_service_unavailable(connector: NewsDataConnector) -> None:
    from app.domain.exceptions import ServiceUnavailableError

    respx.get("https://newsdata.io/api/1/news/search").mock(
        return_value=httpx.Response(401)
    )
    with pytest.raises(ServiceUnavailableError, match="invalid API key"):
        await connector.fetch("test", SINCE)


@pytest.mark.asyncio
@respx.mock
async def test_fetch_429_raises_service_unavailable(connector: NewsDataConnector) -> None:
    from app.domain.exceptions import ServiceUnavailableError

    respx.get("https://newsdata.io/api/1/news/search").mock(
        return_value=httpx.Response(429)
    )
    with pytest.raises(ServiceUnavailableError, match="quota exhausted"):
        await connector.fetch("test", SINCE)


@pytest.mark.asyncio
@respx.mock
async def test_fetch_unexpected_status_raises(connector: NewsDataConnector) -> None:
    from app.domain.exceptions import ServiceUnavailableError

    respx.get("https://newsdata.io/api/1/news/search").mock(
        return_value=httpx.Response(200, json={"status": "error", "results": []})
    )
    with pytest.raises(ServiceUnavailableError, match="unexpected status"):
        await connector.fetch("test", SINCE)


@pytest.mark.asyncio
@respx.mock
async def test_fetch_increments_failure_counter_on_error(
    redis: fakeredis.FakeRedis,
    limiter: RedisRateLimiter,
) -> None:
    connector = NewsDataConnector(
        api_key="test-key",
        source_id=SOURCE_ID,
        rate_limiter=limiter,
    )
    respx.get("https://newsdata.io/api/1/news/search").mock(
        return_value=httpx.Response(500)
    )
    from app.domain.exceptions import ServiceUnavailableError

    with pytest.raises(ServiceUnavailableError):
        await connector.fetch("test", SINCE)

    failures_key = f"vt:cb:failures:{SOURCE_ID}"
    val = await redis.get(failures_key)
    assert val is not None and int(val) >= 1

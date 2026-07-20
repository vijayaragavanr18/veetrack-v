"""Unit tests: workers NewsDataClient — response mapping and HTTP behaviour."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import fakeredis.aioredis as fakeredis
import httpx
import pytest
import respx

from workers.connectors.base import RateLimitExceeded, RedisRateLimiter
from workers.connectors.newsdata import NewsDataClient, _map_article, _parse_published_at

SOURCE_ID = "nd-test"
SINCE = datetime.now(UTC) - timedelta(hours=1)


@pytest.fixture()
async def redis() -> fakeredis.FakeRedis:
    return fakeredis.FakeRedis(decode_responses=False)


@pytest.fixture()
def limiter(redis: fakeredis.FakeRedis) -> RedisRateLimiter:
    return RedisRateLimiter(redis, SOURCE_ID, calls_per_minute=100)


@pytest.fixture()
def client(limiter: RedisRateLimiter) -> NewsDataClient:
    return NewsDataClient(api_key="test-key", source_id=SOURCE_ID, rate_limiter=limiter)


# ---------------------------------------------------------------------------
# _parse_published_at
# ---------------------------------------------------------------------------


def test_parse_valid() -> None:
    dt = _parse_published_at("2024-12-10 09:15:30")
    assert dt.year == 2024 and dt.tzinfo is not None


def test_parse_none_returns_now() -> None:
    dt = _parse_published_at(None)
    assert (datetime.now(UTC) - dt).total_seconds() < 5


def test_parse_bad_format_returns_now() -> None:
    dt = _parse_published_at("garbage")
    assert (datetime.now(UTC) - dt).total_seconds() < 5


# ---------------------------------------------------------------------------
# _map_article
# ---------------------------------------------------------------------------


def test_map_full_item() -> None:
    item = {
        "article_id": "a1",
        "link": "https://example.com",
        "title": "Big News",
        "source_name": "BBC",
        "pubDate": "2024-01-01 12:00:00",
        "content": "Full text",
        "language": "en",
        "image_url": "https://img.example.com/photo.jpg",
    }
    art = _map_article(item)
    assert art is not None
    assert art.headline == "Big News"
    assert art.hero_image_url == "https://img.example.com/photo.jpg"


def test_map_missing_title_is_none() -> None:
    assert _map_article({"article_id": "x", "link": "https://e.com"}) is None


def test_map_missing_url_is_none() -> None:
    assert _map_article({"article_id": "x", "title": "T"}) is None


def test_map_falls_back_to_description() -> None:
    item = {"article_id": "x", "link": "https://e.com", "title": "T", "description": "Desc"}
    art = _map_article(item)
    assert art is not None and art.raw_content == "Desc"


# ---------------------------------------------------------------------------
# NewsDataClient.fetch — HTTP mocked with respx
# ---------------------------------------------------------------------------

_SUCCESS = {
    "status": "success",
    "results": [
        {
            "article_id": "id1",
            "link": "https://newsdata.io/1",
            "title": "Tesla News",
            "source_name": "TC",
            "pubDate": "2026-07-20 13:40:00",
            "language": "en",
        }
    ],
}


@pytest.mark.asyncio
@respx.mock
async def test_fetch_success(client: NewsDataClient) -> None:
    respx.get("https://newsdata.io/api/1/latest").mock(
        return_value=httpx.Response(200, json=_SUCCESS)
    )
    articles = await client.fetch("Tesla", SINCE)
    assert len(articles) == 1
    assert articles[0].headline == "Tesla News"


@pytest.mark.asyncio
@respx.mock
async def test_fetch_skips_invalid_items(client: NewsDataClient) -> None:
    resp_data = {
        "status": "success",
        "results": [
            {"article_id": "ok", "link": "https://e.com", "title": "Valid"},
            {"article_id": "bad"},  # no url or title
        ],
    }
    respx.get("https://newsdata.io/api/1/latest").mock(
        return_value=httpx.Response(200, json=resp_data)
    )
    articles = await client.fetch("test", SINCE)
    assert len(articles) == 1


@pytest.mark.asyncio
@respx.mock
async def test_fetch_429_raises_rate_limit(client: NewsDataClient) -> None:
    respx.get("https://newsdata.io/api/1/latest").mock(return_value=httpx.Response(429))
    with pytest.raises(RateLimitExceeded):
        await client.fetch("test", SINCE)


@pytest.mark.asyncio
@respx.mock
async def test_fetch_401_raises_runtime_error(client: NewsDataClient) -> None:
    respx.get("https://newsdata.io/api/1/latest").mock(return_value=httpx.Response(401))
    with pytest.raises(RuntimeError):
        await client.fetch("test", SINCE)


@pytest.mark.asyncio
@respx.mock
async def test_fetch_records_failure_on_error(
    redis: fakeredis.FakeRedis, limiter: RedisRateLimiter
) -> None:
    c = NewsDataClient(api_key="key", source_id=SOURCE_ID, rate_limiter=limiter)
    respx.get("https://newsdata.io/api/1/latest").mock(return_value=httpx.Response(500))
    with pytest.raises(httpx.HTTPStatusError):
        await c.fetch("test", SINCE)

    val = await redis.get(f"vt:cb:failures:{SOURCE_ID}")
    assert val is not None and int(val) >= 1

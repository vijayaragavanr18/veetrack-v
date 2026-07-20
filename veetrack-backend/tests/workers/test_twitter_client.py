"""Unit tests: workers TwitterClient — response mapping and HTTP behaviour."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import fakeredis.aioredis as fakeredis
import httpx
import pytest
import respx

from workers.connectors.base import RateLimitExceeded, RedisRateLimiter
from workers.connectors.twitter import (
    TwitterClient,
    _extract_media_url,
    _is_retweet,
    _map_tweet,
    _parse_created_at,
)

SOURCE_ID = "tw-test"
SINCE = datetime.now(UTC) - timedelta(hours=1)


@pytest.fixture()
async def redis() -> fakeredis.FakeRedis:
    return fakeredis.FakeRedis(decode_responses=False)


@pytest.fixture()
def limiter(redis: fakeredis.FakeRedis) -> RedisRateLimiter:
    return RedisRateLimiter(redis, SOURCE_ID, calls_per_minute=100)


@pytest.fixture()
def client(limiter: RedisRateLimiter) -> TwitterClient:
    return TwitterClient(api_key="test-key", source_id=SOURCE_ID, rate_limiter=limiter)


# _parse_created_at


def test_parse_with_microseconds() -> None:
    dt = _parse_created_at("2024-12-10T09:15:30.000Z")
    assert dt.year == 2024 and dt.tzinfo is not None


def test_parse_fallback() -> None:
    dt = _parse_created_at("2024-12-10T09:15:30Z")
    assert dt.year == 2024


def test_parse_none() -> None:
    dt = _parse_created_at(None)
    assert (datetime.now(UTC) - dt).total_seconds() < 5


# _is_retweet


def test_is_retweet() -> None:
    assert _is_retweet({"referenced_tweets": [{"type": "retweeted"}]}) is True


def test_not_retweet() -> None:
    assert _is_retweet({"referenced_tweets": [{"type": "replied_to"}]}) is False


def test_no_refs() -> None:
    assert _is_retweet({}) is False


# _extract_media_url


def test_extract_photo_url() -> None:
    tweet = {
        "attachments": {"media_keys": ["k1"]},
        "_includes": {"media": [{"media_key": "k1", "url": "https://img.example.com/photo.jpg"}]},
    }
    assert _extract_media_url(tweet) == "https://img.example.com/photo.jpg"


def test_extract_no_media() -> None:
    assert _extract_media_url({}) is None


# _map_tweet

_T = {
    "id": "1",
    "text": "Hello world #Tesla",
    "author": {"userName": "user1", "name": "User", "followers_count": 100},
    "created_at": "2024-12-10T10:00:00Z",
    "lang": "en",
    "public_metrics": {"retweet_count": 1, "like_count": 5, "reply_count": 0},
}


def test_map_full() -> None:
    a = _map_tweet(_T)
    assert a is not None
    assert a.publisher == "Twitter/X"
    assert a.metadata_json["author_username"] == "user1"
    assert a.metadata_json["like_count"] == 5


def test_map_retweet_is_none() -> None:
    rt = {**_T, "referenced_tweets": [{"type": "retweeted"}]}
    assert _map_tweet(rt) is None


def test_map_missing_id() -> None:
    assert _map_tweet({"text": "hi"}) is None


def test_map_missing_text() -> None:
    assert _map_tweet({"id": "1"}) is None


def test_map_non_english() -> None:
    tw = {**_T, "lang": "ja", "id": "2"}
    a = _map_tweet(tw)
    assert a is not None and a.language == "ja"


def test_map_deleted_user() -> None:
    tw = {**_T, "author": None, "id": "3"}
    a = _map_tweet(tw)
    assert a is not None and "unknown" in a.url


def test_map_long_text_truncated() -> None:
    tw = {**_T, "text": "x" * 500, "id": "4"}
    a = _map_tweet(tw)
    assert a is not None
    assert len(a.headline) == 280
    assert len(a.raw_content) == 500


# TwitterClient.fetch — HTTP mocked

_RESP = {
    "tweets": [
        {
            "id": "t1",
            "text": "Tesla news today",
            "author": {"userName": "newsbot", "name": "News Bot"},
            "created_at": "2024-12-10T10:00:00Z",
            "lang": "en",
            "public_metrics": {},
        }
    ]
}

_RT_RESP = {
    "tweets": [
        {
            "id": "rt1",
            "text": "RT @orig: Tesla news",
            "author": {"userName": "retweeter"},
            "created_at": "2024-12-10T10:00:00Z",
            "lang": "en",
            "referenced_tweets": [{"type": "retweeted"}],
            "public_metrics": {},
        }
    ]
}


@pytest.mark.asyncio
@respx.mock
async def test_fetch_success(client: TwitterClient) -> None:
    respx.get("https://api.twitterapi.io/twitter/tweet/advanced_search").mock(
        return_value=httpx.Response(200, json=_RESP)
    )
    articles = await client.fetch("Tesla", SINCE)
    assert len(articles) == 1
    assert articles[0].external_id == "t1"


@pytest.mark.asyncio
@respx.mock
async def test_fetch_retweets_filtered(client: TwitterClient) -> None:
    respx.get("https://api.twitterapi.io/twitter/tweet/advanced_search").mock(
        return_value=httpx.Response(200, json=_RT_RESP)
    )
    articles = await client.fetch("Tesla", SINCE)
    assert len(articles) == 0


@pytest.mark.asyncio
@respx.mock
async def test_fetch_429_raises(client: TwitterClient) -> None:
    respx.get("https://api.twitterapi.io/twitter/tweet/advanced_search").mock(
        return_value=httpx.Response(429)
    )
    with pytest.raises(RateLimitExceeded):
        await client.fetch("Tesla", SINCE)


@pytest.mark.asyncio
@respx.mock
async def test_fetch_401_raises(client: TwitterClient) -> None:
    respx.get("https://api.twitterapi.io/twitter/tweet/advanced_search").mock(
        return_value=httpx.Response(401)
    )
    with pytest.raises(RuntimeError, match="auth error"):
        await client.fetch("Tesla", SINCE)


@pytest.mark.asyncio
@respx.mock
async def test_fetch_records_failure(redis: fakeredis.FakeRedis, limiter: RedisRateLimiter) -> None:
    c = TwitterClient(api_key="key", source_id=SOURCE_ID, rate_limiter=limiter)
    respx.get("https://api.twitterapi.io/twitter/tweet/advanced_search").mock(
        return_value=httpx.Response(500)
    )
    with pytest.raises(httpx.HTTPStatusError):
        await c.fetch("Tesla", SINCE)

    val = await redis.get(f"vt:cb:failures:{SOURCE_ID}")
    assert val is not None and int(val) >= 1

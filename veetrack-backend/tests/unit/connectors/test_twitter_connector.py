"""Unit tests: TwitterConnector response mapping + HTTP behaviour (respx mocks)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import fakeredis.aioredis as fakeredis
import httpx
import pytest
import respx

from app.infrastructure.connectors.base import RedisRateLimiter
from app.infrastructure.connectors.twitter_connector import (
    TwitterConnector,
    _extract_media_url,
    _is_retweet,
    _map_tweet,
    _parse_created_at,
    _tweet_url,
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
def connector(limiter: RedisRateLimiter) -> TwitterConnector:
    return TwitterConnector(
        api_key="test-key",
        source_id=SOURCE_ID,
        rate_limiter=limiter,
    )


# ---------------------------------------------------------------------------
# _parse_created_at
# ---------------------------------------------------------------------------


def test_parse_with_microseconds() -> None:
    dt = _parse_created_at("2024-12-10T09:15:30.000Z")
    assert dt.year == 2024 and dt.tzinfo is not None


def test_parse_without_microseconds() -> None:
    dt = _parse_created_at("2024-12-10T09:15:30Z")
    assert dt.year == 2024 and dt.tzinfo is not None


def test_parse_none_returns_now() -> None:
    dt = _parse_created_at(None)
    assert (datetime.now(UTC) - dt).total_seconds() < 5


def test_parse_bad_format_returns_now() -> None:
    dt = _parse_created_at("not-a-date")
    assert (datetime.now(UTC) - dt).total_seconds() < 5


# ---------------------------------------------------------------------------
# _is_retweet
# ---------------------------------------------------------------------------


def test_is_retweet_true() -> None:
    tweet = {"referenced_tweets": [{"type": "retweeted", "id": "123"}]}
    assert _is_retweet(tweet) is True


def test_is_retweet_false_for_reply() -> None:
    tweet = {"referenced_tweets": [{"type": "replied_to", "id": "123"}]}
    assert _is_retweet(tweet) is False


def test_is_retweet_false_no_refs() -> None:
    assert _is_retweet({}) is False


# ---------------------------------------------------------------------------
# _extract_media_url
# ---------------------------------------------------------------------------


def test_extract_media_url_photo() -> None:
    tweet = {
        "attachments": {"media_keys": ["key1"]},
        "_includes": {
            "media": [{"media_key": "key1", "url": "https://pbs.twimg.com/media/img.jpg"}]
        },
    }
    assert _extract_media_url(tweet) == "https://pbs.twimg.com/media/img.jpg"


def test_extract_media_url_preview_image() -> None:
    tweet = {
        "attachments": {"media_keys": ["key1"]},
        "_includes": {
            "media": [{"media_key": "key1", "preview_image_url": "https://pbs.twimg.com/thumb.jpg"}]
        },
    }
    assert _extract_media_url(tweet) == "https://pbs.twimg.com/thumb.jpg"


def test_extract_media_url_no_media() -> None:
    assert _extract_media_url({}) is None


def test_extract_media_url_missing_key() -> None:
    tweet = {
        "attachments": {"media_keys": ["missing"]},
        "_includes": {"media": [{"media_key": "other", "url": "https://example.com"}]},
    }
    assert _extract_media_url(tweet) is None


# ---------------------------------------------------------------------------
# _tweet_url
# ---------------------------------------------------------------------------


def test_tweet_url_with_author() -> None:
    tweet = {"id": "456", "author": {"userName": "elonmusk"}}
    assert _tweet_url(tweet) == "https://twitter.com/elonmusk/status/456"


def test_tweet_url_unknown_author() -> None:
    tweet = {"id": "789", "author": {}}
    assert "unknown" in _tweet_url(tweet)


# ---------------------------------------------------------------------------
# _map_tweet
# ---------------------------------------------------------------------------

_TWEET = {
    "id": "111",
    "text": "Tesla Autopilot update rolling out now! $TSLA",
    "author": {"userName": "teslanews", "name": "Tesla News", "followers_count": 50000},
    "created_at": "2024-12-10T10:00:00Z",
    "lang": "en",
    "public_metrics": {"retweet_count": 10, "like_count": 100, "reply_count": 5},
}


def test_map_tweet_full() -> None:
    article = _map_tweet(_TWEET)
    assert article is not None
    assert article.external_id == "111"
    assert article.publisher == "Twitter/X"
    assert article.language == "en"
    assert article.metadata_json["retweet_count"] == 10
    assert article.metadata_json["like_count"] == 100
    assert article.metadata_json["author_username"] == "teslanews"


def test_map_tweet_retweet_returns_none() -> None:
    rt = {**_TWEET, "referenced_tweets": [{"type": "retweeted", "id": "99"}]}
    assert _map_tweet(rt) is None


def test_map_tweet_missing_id_returns_none() -> None:
    assert _map_tweet({"text": "hello"}) is None


def test_map_tweet_missing_text_returns_none() -> None:
    assert _map_tweet({"id": "1"}) is None


def test_map_tweet_no_media_is_none() -> None:
    article = _map_tweet(_TWEET)
    assert article is not None
    assert article.hero_image_url is None


def test_map_tweet_non_english() -> None:
    tweet = {**_TWEET, "lang": "de", "id": "222"}
    article = _map_tweet(tweet)
    assert article is not None
    assert article.language == "de"


def test_map_tweet_deleted_user_placeholder() -> None:
    tweet = {**_TWEET, "author": None, "id": "333"}
    article = _map_tweet(tweet)
    assert article is not None
    assert "unknown" in article.url


def test_map_tweet_long_text_truncated_headline() -> None:
    long_text = "x" * 500
    tweet = {**_TWEET, "text": long_text, "id": "444"}
    article = _map_tweet(tweet)
    assert article is not None
    assert len(article.headline) == 280
    assert article.raw_content == long_text  # full text preserved


# ---------------------------------------------------------------------------
# TwitterConnector.fetch — HTTP mocked with respx
# ---------------------------------------------------------------------------

_GOOD_RESPONSE = {
    "tweets": [
        {
            "id": "t001",
            "text": "Tesla stock up 5% today #TSLA",
            "author": {"userName": "stocknews", "name": "Stock News", "followers_count": 10000},
            "created_at": "2024-12-10T10:00:00Z",
            "lang": "en",
            "public_metrics": {"retweet_count": 5, "like_count": 50, "reply_count": 2},
        }
    ],
    "has_next_page": False,
}

_RETWEET_RESPONSE = {
    "tweets": [
        {
            "id": "rt001",
            "text": "RT @original: Tesla news",
            "author": {"userName": "retweeter", "name": "RT User"},
            "created_at": "2024-12-10T10:00:00Z",
            "lang": "en",
            "referenced_tweets": [{"type": "retweeted", "id": "original001"}],
            "public_metrics": {},
        }
    ],
    "has_next_page": False,
}


@pytest.mark.asyncio
@respx.mock
async def test_fetch_success(connector: TwitterConnector) -> None:
    respx.get("https://api.twitterapi.io/twitter/tweet/advanced_search").mock(
        return_value=httpx.Response(200, json=_GOOD_RESPONSE)
    )
    articles = await connector.fetch("Tesla", SINCE)
    assert len(articles) == 1
    assert articles[0].external_id == "t001"
    assert articles[0].publisher == "Twitter/X"


@pytest.mark.asyncio
@respx.mock
async def test_fetch_filters_retweets(connector: TwitterConnector) -> None:
    respx.get("https://api.twitterapi.io/twitter/tweet/advanced_search").mock(
        return_value=httpx.Response(200, json=_RETWEET_RESPONSE)
    )
    articles = await connector.fetch("Tesla", SINCE)
    assert len(articles) == 0


@pytest.mark.asyncio
@respx.mock
async def test_fetch_empty_response(connector: TwitterConnector) -> None:
    respx.get("https://api.twitterapi.io/twitter/tweet/advanced_search").mock(
        return_value=httpx.Response(200, json={"tweets": [], "has_next_page": False})
    )
    articles = await connector.fetch("Tesla", SINCE)
    assert articles == []


@pytest.mark.asyncio
@respx.mock
async def test_fetch_401_raises_service_unavailable(connector: TwitterConnector) -> None:
    from app.domain.exceptions import ServiceUnavailableError

    respx.get("https://api.twitterapi.io/twitter/tweet/advanced_search").mock(
        return_value=httpx.Response(401)
    )
    with pytest.raises(ServiceUnavailableError, match="auth error"):
        await connector.fetch("Tesla", SINCE)


@pytest.mark.asyncio
@respx.mock
async def test_fetch_429_raises_service_unavailable(connector: TwitterConnector) -> None:
    from app.domain.exceptions import ServiceUnavailableError

    respx.get("https://api.twitterapi.io/twitter/tweet/advanced_search").mock(
        return_value=httpx.Response(429)
    )
    with pytest.raises(ServiceUnavailableError, match="quota exhausted"):
        await connector.fetch("Tesla", SINCE)


@pytest.mark.asyncio
@respx.mock
async def test_fetch_increments_failure_counter(
    redis: fakeredis.FakeRedis,
    limiter: RedisRateLimiter,
) -> None:
    conn = TwitterConnector(api_key="key", source_id=SOURCE_ID, rate_limiter=limiter)
    respx.get("https://api.twitterapi.io/twitter/tweet/advanced_search").mock(
        return_value=httpx.Response(500)
    )
    from app.domain.exceptions import ServiceUnavailableError

    with pytest.raises(ServiceUnavailableError):
        await conn.fetch("Tesla", SINCE)

    val = await redis.get(f"vt:cb:failures:{SOURCE_ID}")
    assert val is not None and int(val) >= 1

"""TwitterAPI.io HTTP client for the workers package.

Mirrors apps/api/app/infrastructure/connectors/twitter_connector.py in behaviour.
Retweets are filtered at source level to avoid duplicate ingestion.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx
import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from workers.connectors.base import CircuitOpen, RateLimitExceeded, RedisRateLimiter

logger = structlog.get_logger(__name__)

_BASE_URL = "https://api.twitterapi.io"
_SEARCH_PATH = "/twitter/tweet/advanced_search"

_RETRY_POLICY = dict(
    retry=retry_if_exception_type((httpx.TransportError, httpx.TimeoutException)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    reraise=True,
)

_PUBLISHER = "Twitter/X"
_TWITTER_DATE_FMT = "%Y-%m-%dT%H:%M:%S.%fZ"
_TWITTER_DATE_FMT_FALLBACK = "%Y-%m-%dT%H:%M:%SZ"


@dataclass
class RawArticle:
    external_id: str
    url: str
    headline: str
    publisher: str
    published_at: datetime
    raw_content: str
    language: str = "en"
    hero_image_url: str | None = None
    metadata_json: dict[str, object] = field(default_factory=dict)


def _parse_created_at(raw: str | None) -> datetime:
    if not raw:
        return datetime.now(UTC)
    for fmt in (_TWITTER_DATE_FMT, _TWITTER_DATE_FMT_FALLBACK):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return datetime.now(UTC)


def _extract_media_url(tweet: dict[str, Any]) -> str | None:
    attachments = tweet.get("attachments") or {}
    media_keys = attachments.get("media_keys") or []
    includes = tweet.get("_includes") or {}
    media_list: list[dict[str, Any]] = includes.get("media") or []
    media_map = {m.get("media_key"): m for m in media_list}
    for key in media_keys:
        m = media_map.get(key)
        if m is None:
            continue
        url: str | None = m.get("url") or m.get("preview_image_url")
        if url:
            return url
    return None


def _is_retweet(tweet: dict[str, Any]) -> bool:
    refs: list[dict[str, Any]] = tweet.get("referenced_tweets") or []
    return any(r.get("type") == "retweeted" for r in refs)


def _tweet_url(tweet: dict[str, Any]) -> str:
    tweet_id = str(tweet.get("id") or "")
    author: dict[str, Any] = tweet.get("author") or {}
    username = str(author.get("userName") or author.get("username") or "unknown")
    return f"https://twitter.com/{username}/status/{tweet_id}"


def _map_tweet(tweet: dict[str, Any]) -> RawArticle | None:
    tweet_id: str | None = str(tweet.get("id")) if tweet.get("id") else None
    text: str | None = tweet.get("text")
    if not tweet_id or not text:
        return None
    if _is_retweet(tweet):
        return None

    author: dict[str, Any] = tweet.get("author") or {}
    lang = str(tweet.get("lang") or "en")
    url = _tweet_url(tweet)

    public_metrics: dict[str, Any] = tweet.get("public_metrics") or {}
    metadata: dict[str, object] = {
        "retweet_count": public_metrics.get("retweet_count", 0),
        "like_count": public_metrics.get("like_count", 0),
        "reply_count": public_metrics.get("reply_count", 0),
        "author_username": str(author.get("userName") or author.get("username") or ""),
        "author_followers": author.get("followers_count", 0),
    }

    return RawArticle(
        external_id=tweet_id,
        url=url,
        headline=text[:280],
        publisher=_PUBLISHER,
        published_at=_parse_created_at(tweet.get("created_at")),
        raw_content=text,
        language=lang,
        hero_image_url=_extract_media_url(tweet),
        metadata_json=metadata,
    )


class TwitterClient:
    """Async HTTP client for TwitterAPI.io, with rate limiting and retry."""

    def __init__(
        self,
        api_key: str,
        source_id: str,
        rate_limiter: RedisRateLimiter,
        *,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key
        self._source_id = source_id
        self._limiter = rate_limiter
        self._http = http_client or httpx.AsyncClient(timeout=30.0)

    async def fetch(self, query: str, since: datetime) -> list[RawArticle]:
        await self._limiter.acquire()
        try:
            articles = await self._do_fetch(query, since)
            await self._limiter.record_success()
            return articles
        except (CircuitOpen, RateLimitExceeded):
            raise
        except Exception as exc:
            await self._limiter.record_failure()
            logger.warning(
                "connector.twitter.fetch_failed",
                source_id=self._source_id,
                query=query,
                error=str(exc),
            )
            raise

    @retry(**_RETRY_POLICY)
    async def _do_fetch(self, query: str, since: datetime) -> list[RawArticle]:
        since_str = since.strftime("%Y-%m-%d")
        full_query = f"{query} since:{since_str}"
        resp = await self._http.get(
            f"{_BASE_URL}{_SEARCH_PATH}",
            params={"query": full_query, "queryType": "Latest"},
            headers={"X-API-Key": self._api_key},
        )

        if resp.status_code in (401, 403):
            raise RuntimeError(f"TwitterAPI.io: auth error {resp.status_code}")
        if resp.status_code == 429:
            raise RateLimitExceeded("TwitterAPI.io: quota exhausted (429)")
        if resp.status_code >= 500:
            raise httpx.HTTPStatusError(
                f"TwitterAPI.io server error {resp.status_code}",
                request=resp.request,
                response=resp,
            )
        resp.raise_for_status()

        data: dict[str, Any] = resp.json()
        tweets: list[dict[str, Any]] = data.get("tweets") or []

        results = []
        for tweet in tweets:
            article = _map_tweet(tweet)
            if article is not None:
                results.append(article)

        logger.info(
            "connector.twitter.fetched",
            source_id=self._source_id,
            query=query,
            total=len(tweets),
            mapped=len(results),
        )
        return results

"""TwitterAPI.io source connector.

Maps TwitterAPI.io `/twitter/search/tweet` responses to the common RawArticle DTO.
Twitter-specific fields (retweet count, like count, author handle, is_retweet flag)
are stored in RawArticle.metadata_json — they never alter the shared DTO shape.

Retweet dedup: retweets carry a `referenced_tweets` entry with type="retweeted".
We skip them at source level so the same original tweet isn't ingested twice from
different retweeter accounts.

API docs: https://twitterapi.io/documentation
"""

from __future__ import annotations

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

from app.domain.entities import QuotaStatus, RawArticle
from app.domain.exceptions import ServiceUnavailableError
from app.infrastructure.connectors.base import RedisRateLimiter

logger = structlog.get_logger(__name__)

_BASE_URL = "https://api.twitterapi.io"
_SEARCH_PATH = "/twitter/tweet/advanced_search"

_DEFAULT_CALLS_PER_MINUTE = 15
_PUBLISHER = "Twitter/X"

# ISO 8601 format used by Twitter API v2
_TWITTER_DATE_FMT = "%Y-%m-%dT%H:%M:%S.%fZ"
_TWITTER_DATE_FMT_FALLBACK = "%Y-%m-%dT%H:%M:%SZ"


def _parse_created_at(raw: str | None) -> datetime:
    """Parse Twitter's ISO-8601 created_at to UTC datetime."""
    if not raw:
        return datetime.now(UTC)
    for fmt in (_TWITTER_DATE_FMT, _TWITTER_DATE_FMT_FALLBACK):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return datetime.now(UTC)


def _extract_media_url(tweet: dict[str, Any]) -> str | None:
    """Return the first photo/video thumbnail URL from tweet attachments, or None."""
    attachments = tweet.get("attachments") or {}
    media_keys = attachments.get("media_keys") or []
    includes = tweet.get("_includes") or {}
    media_list: list[dict[str, Any]] = includes.get("media") or []
    # Build lookup by media_key
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
    """True if this tweet is a retweet of another tweet."""
    refs: list[dict[str, Any]] = tweet.get("referenced_tweets") or []
    return any(r.get("type") == "retweeted" for r in refs)


def _tweet_url(tweet: dict[str, Any]) -> str:
    """Construct the canonical tweet URL from author username + tweet id."""
    tweet_id: str = str(tweet.get("id") or "")
    author: dict[str, Any] = tweet.get("author") or tweet.get("author_id") or {}
    if isinstance(author, dict):
        username: str = str(author.get("userName") or author.get("username") or "unknown")
    else:
        username = "unknown"
    return f"https://twitter.com/{username}/status/{tweet_id}"


def _map_tweet(tweet: dict[str, Any]) -> RawArticle | None:
    """Map a single tweet dict to RawArticle; return None if invalid or a retweet."""
    tweet_id: str | None = str(tweet.get("id")) if tweet.get("id") else None
    text: str | None = tweet.get("text")
    if not tweet_id or not text:
        return None

    # Skip bare retweets — the original will be (or was already) ingested directly.
    if _is_retweet(tweet):
        return None

    author: dict[str, Any] = tweet.get("author") or {}
    lang: str = str(tweet.get("lang") or "en")
    url = _tweet_url(tweet)

    # Engagement metrics go into metadata_json, not the DTO proper.
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
        headline=text[:280],  # tweet text as headline; full text in raw_content
        publisher=_PUBLISHER,
        published_at=_parse_created_at(tweet.get("created_at")),
        raw_content=text,
        language=lang,
        hero_image_url=_extract_media_url(tweet),
        metadata_json=metadata,
    )


class TwitterConnector:
    """Concrete SourceConnector for TwitterAPI.io.

    Searches recent tweets matching a keyword/query string.
    Rate limiting and circuit breaking are delegated to RedisRateLimiter.
    """

    source_type = "twitter"

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
        """Pull tweets matching *query* posted after *since*.

        Rate-limited and circuit-broken via RedisRateLimiter.
        """
        await self._limiter.acquire()
        try:
            articles: list[RawArticle] = await self._fetch_with_retry(query, since)
            await self._limiter.record_success()
            return articles
        except ServiceUnavailableError:
            raise
        except Exception as exc:
            await self._limiter.record_failure()
            logger.warning(
                "connector.twitter.fetch_failed",
                source_id=self._source_id,
                query=query,
                error=str(exc),
            )
            raise ServiceUnavailableError(f"TwitterAPI.io fetch failed: {exc}") from exc

    async def remaining_quota(self) -> QuotaStatus:
        calls = await self._limiter.calls_this_window()
        open_until = await self._limiter.circuit_open_until()
        now = datetime.now(UTC)
        minute_start = now.replace(second=0, microsecond=0)
        return QuotaStatus(
            source_id=self._source_id,
            calls_made=calls,
            quota_limit=_DEFAULT_CALLS_PER_MINUTE,
            window_start=minute_start,
            circuit_open=open_until is not None,
            circuit_open_until=open_until,
        )

    @retry(
        retry=retry_if_exception_type((httpx.TransportError, httpx.TimeoutException)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
    async def _fetch_with_retry(
        self, query: str, since: datetime
    ) -> list[RawArticle]:
        # TwitterAPI.io advanced search uses `query` param with Twitter search syntax.
        # We append a `since:YYYY-MM-DD` operator to bound the time window.
        since_str = since.strftime("%Y-%m-%d")
        full_query = f"{query} since:{since_str}"
        params: dict[str, str] = {
            "query": full_query,
            "queryType": "Latest",
        }
        resp = await self._http.get(
            f"{_BASE_URL}{_SEARCH_PATH}",
            params=params,
            headers={"X-API-Key": self._api_key},
        )

        if resp.status_code in (401, 403):
            raise ServiceUnavailableError(
                f"TwitterAPI.io: auth error {resp.status_code}"
            )
        if resp.status_code == 429:
            raise ServiceUnavailableError("TwitterAPI.io: quota exhausted (429)")
        if resp.status_code >= 500:
            raise httpx.HTTPStatusError(
                f"TwitterAPI.io server error {resp.status_code}",
                request=resp.request,
                response=resp,
            )
        resp.raise_for_status()

        data: dict[str, Any] = resp.json()
        # TwitterAPI.io returns {"tweets": [...], "has_next_page": bool, ...}
        tweets: list[dict[str, Any]] = data.get("tweets") or []

        results: list[RawArticle] = []
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

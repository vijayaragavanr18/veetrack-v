"""Unit tests: workers YouTubeClient — mapping and yt-dlp mocking."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import fakeredis.aioredis as fakeredis
import pytest

from connectors.base import RedisRateLimiter
from connectors.youtube import (
    YouTubeClient,
    _build_transcript_text,
    _parse_upload_date,
    _stable_external_id,
    _video_url,
    map_video_to_article,
)

SOURCE_ID = "yt-workers-test"
SINCE = datetime(2020, 1, 1, tzinfo=UTC)


@pytest.fixture()
async def redis() -> fakeredis.FakeRedis:
    return fakeredis.FakeRedis(decode_responses=False)


@pytest.fixture()
def limiter(redis: fakeredis.FakeRedis) -> RedisRateLimiter:
    return RedisRateLimiter(redis, SOURCE_ID, calls_per_minute=100)


def _make_client(
    limiter: RedisRateLimiter,
    *,
    search_fn: object | None = None,
    transcript_api: object | None = None,
) -> YouTubeClient:
    return YouTubeClient(
        source_id=SOURCE_ID,
        rate_limiter=limiter,
        search_fn=search_fn,
        transcript_api=transcript_api,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def test_video_url() -> None:
    assert _video_url("abc") == "https://www.youtube.com/watch?v=abc"


def test_stable_external_id() -> None:
    assert _stable_external_id("x") == "yt:x"


def test_parse_upload_date_valid() -> None:
    dt = _parse_upload_date("20240301")
    assert dt.year == 2024 and dt.month == 3


def test_parse_upload_date_none() -> None:
    dt = _parse_upload_date(None)
    assert (datetime.now(UTC) - dt).total_seconds() < 5


def test_build_transcript_text() -> None:
    s1, s2 = MagicMock(text="Hello"), MagicMock(text=" world ")
    assert _build_transcript_text([s1, s2]) == "Hello world"


def test_build_transcript_text_empty() -> None:
    assert _build_transcript_text([]) == ""


# ---------------------------------------------------------------------------
# map_video_to_article
# ---------------------------------------------------------------------------

_INFO = {
    "title": "Apple WWDC",
    "channel": "TechNews",
    "upload_date": "20240610",
    "description": "Summary",
    "thumbnails": [{"url": "https://i.ytimg.com/vi/v1/hq.jpg"}],
}


def test_map_video_to_article_fields() -> None:
    a = map_video_to_article("v1", _INFO, "Great keynote", "en", True)
    assert a.external_id == "yt:v1"
    assert a.headline == "Apple WWDC"
    assert a.publisher == "TechNews"
    assert a.raw_content == "Great keynote"
    assert a.metadata_json["is_generated_transcript"] is True


def test_map_video_to_article_no_thumbnails() -> None:
    info = {**_INFO, "thumbnails": []}
    a = map_video_to_article("v", info, "t", "en", False)
    assert a.hero_image_url is None


def test_map_video_to_article_falls_back_to_uploader() -> None:
    info = {**_INFO, "channel": None, "uploader": "FallbackChannel"}
    a = map_video_to_article("v", info, "t", "en", False)
    assert a.publisher == "FallbackChannel"


# ---------------------------------------------------------------------------
# YouTubeClient.fetch
# ---------------------------------------------------------------------------

def _make_video(vid_id: str, upload_date: str = "20241210") -> dict:
    return {
        "id": vid_id,
        "title": f"Vid {vid_id}",
        "channel": "Ch",
        "upload_date": upload_date,
        "description": "",
        "thumbnails": [],
    }


def _make_fetched(text: str = "transcript") -> MagicMock:
    s = MagicMock()
    s.text = text
    f = MagicMock()
    f.snippets = [s]
    f.language_code = "en"
    f.is_generated = False
    return f


@pytest.mark.asyncio
async def test_fetch_success(limiter: RedisRateLimiter) -> None:
    search_fn = MagicMock(return_value=[_make_video("v1")])
    api = MagicMock()
    api.fetch.return_value = _make_fetched("Hello transcript")
    client = _make_client(limiter, search_fn=search_fn, transcript_api=api)

    articles = await client.fetch("Apple", SINCE)
    assert len(articles) == 1
    assert articles[0].external_id == "yt:v1"


@pytest.mark.asyncio
async def test_fetch_skips_transcript_disabled(limiter: RedisRateLimiter) -> None:
    from youtube_transcript_api import TranscriptsDisabled

    search_fn = MagicMock(return_value=[_make_video("v1"), _make_video("v2")])
    api = MagicMock()
    api.fetch.side_effect = [TranscriptsDisabled("v1"), _make_fetched("v2 text")]
    client = _make_client(limiter, search_fn=search_fn, transcript_api=api)

    articles = await client.fetch("Apple", SINCE)
    assert len(articles) == 1
    assert articles[0].external_id == "yt:v2"


@pytest.mark.asyncio
async def test_fetch_skips_no_transcript_found(limiter: RedisRateLimiter) -> None:
    from youtube_transcript_api import NoTranscriptFound

    search_fn = MagicMock(return_value=[_make_video("v1")])
    api = MagicMock()
    api.fetch.side_effect = NoTranscriptFound("v1", ["en"], [])
    client = _make_client(limiter, search_fn=search_fn, transcript_api=api)

    articles = await client.fetch("Apple", SINCE)
    assert articles == []


@pytest.mark.asyncio
async def test_fetch_skips_video_unavailable(limiter: RedisRateLimiter) -> None:
    from youtube_transcript_api import VideoUnavailable

    search_fn = MagicMock(return_value=[_make_video("v1")])
    api = MagicMock()
    api.fetch.side_effect = VideoUnavailable("v1")
    client = _make_client(limiter, search_fn=search_fn, transcript_api=api)

    articles = await client.fetch("Apple", SINCE)
    assert articles == []


@pytest.mark.asyncio
async def test_fetch_empty_results(limiter: RedisRateLimiter) -> None:
    search_fn = MagicMock(return_value=[])
    client = _make_client(limiter, search_fn=search_fn)

    articles = await client.fetch("Apple", SINCE)
    assert articles == []


@pytest.mark.asyncio
async def test_fetch_filters_old_videos(limiter: RedisRateLimiter) -> None:
    old_vid = _make_video("v1", upload_date="20180101")
    search_fn = MagicMock(return_value=[old_vid])
    client = _make_client(limiter, search_fn=search_fn)

    articles = await client.fetch("Apple", since=datetime(2024, 1, 1, tzinfo=UTC))
    assert articles == []


@pytest.mark.asyncio
async def test_fetch_search_failure_raises(limiter: RedisRateLimiter) -> None:
    search_fn = MagicMock(side_effect=RuntimeError("network error"))
    client = _make_client(limiter, search_fn=search_fn)

    with pytest.raises(Exception, match="yt-dlp search failed"):
        await client.fetch("Apple", SINCE)


@pytest.mark.asyncio
async def test_fetch_records_failure_on_error(
    redis: fakeredis.FakeRedis, limiter: RedisRateLimiter
) -> None:
    search_fn = MagicMock(side_effect=RuntimeError("boom"))
    client = _make_client(limiter, search_fn=search_fn)

    with pytest.raises(Exception):
        await client.fetch("Apple", SINCE)

    val = await redis.get(f"vt:cb:failures:{SOURCE_ID}")
    assert val is not None and int(val) >= 1


@pytest.mark.asyncio
async def test_fetch_mixed_batch(limiter: RedisRateLimiter) -> None:
    from youtube_transcript_api import TranscriptsDisabled

    search_fn = MagicMock(
        return_value=[_make_video("v1"), _make_video("v2"), _make_video("v3")]
    )
    api = MagicMock()
    api.fetch.side_effect = [
        _make_fetched("v1 transcript"),
        TranscriptsDisabled("v2"),
        _make_fetched("v3 transcript"),
    ]
    client = _make_client(limiter, search_fn=search_fn, transcript_api=api)

    articles = await client.fetch("Apple", SINCE)
    assert len(articles) == 2
    assert {a.external_id for a in articles} == {"yt:v1", "yt:v3"}

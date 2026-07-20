"""Unit tests: YouTubeConnector — mapping, transcript skip, yt-dlp mocking."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import fakeredis.aioredis as fakeredis
import pytest

from app.domain.exceptions import ServiceUnavailableError
from app.infrastructure.connectors.base import RedisRateLimiter
from app.infrastructure.connectors.youtube_connector import (
    YouTubeConnector,
    _build_transcript_text,
    _parse_upload_date,
    _stable_external_id,
    _video_url,
    map_video_to_article,
)

SOURCE_ID = "yt-test"
SINCE = datetime(2020, 1, 1, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
async def redis() -> fakeredis.FakeRedis:
    return fakeredis.FakeRedis(decode_responses=False)


@pytest.fixture()
def limiter(redis: fakeredis.FakeRedis) -> RedisRateLimiter:
    return RedisRateLimiter(redis, SOURCE_ID, calls_per_minute=100)


def _make_connector(
    limiter: RedisRateLimiter,
    *,
    search_fn: object | None = None,
    transcript_api: object | None = None,
) -> YouTubeConnector:
    return YouTubeConnector(
        source_id=SOURCE_ID,
        rate_limiter=limiter,
        search_fn=search_fn,
        transcript_api=transcript_api,
    )


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

def test_video_url() -> None:
    assert _video_url("dQw4w9WgXcQ") == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def test_stable_external_id() -> None:
    assert _stable_external_id("abc123") == "yt:abc123"


def test_parse_upload_date_valid() -> None:
    dt = _parse_upload_date("20241215")
    assert dt.year == 2024 and dt.month == 12 and dt.day == 15 and dt.tzinfo is not None


def test_parse_upload_date_none_returns_now() -> None:
    dt = _parse_upload_date(None)
    assert (datetime.now(UTC) - dt).total_seconds() < 5


def test_parse_upload_date_bad_format_returns_now() -> None:
    dt = _parse_upload_date("not-a-date")
    assert (datetime.now(UTC) - dt).total_seconds() < 5


def test_build_transcript_text_joins_snippets() -> None:
    snippets = [
        MagicMock(text="Hello world"),
        MagicMock(text="  how are you  "),
        MagicMock(text=""),
    ]
    result = _build_transcript_text(snippets)
    assert result == "Hello world how are you"


def test_build_transcript_text_empty() -> None:
    assert _build_transcript_text([]) == ""


# ---------------------------------------------------------------------------
# map_video_to_article
# ---------------------------------------------------------------------------

_INFO = {
    "title": "Tesla Earnings Q4 2024",
    "channel": "Finance Today",
    "upload_date": "20241210",
    "description": "Deep dive",
    "thumbnails": [
        {"url": "https://i.ytimg.com/vi/abc/hq.jpg"},
        {"url": "https://i.ytimg.com/vi/abc/maxres.jpg"},
    ],
}


def test_map_video_to_article_full() -> None:
    a = map_video_to_article(
        video_id="abc123",
        info=_INFO,
        transcript_text="Tesla beat estimates",
        language="en",
        is_generated=False,
    )
    assert a.external_id == "yt:abc123"
    assert a.headline == "Tesla Earnings Q4 2024"
    assert a.publisher == "Finance Today"
    assert a.url == "https://www.youtube.com/watch?v=abc123"
    assert a.raw_content == "Tesla beat estimates"
    assert a.language == "en"
    # last thumbnail in list
    assert a.hero_image_url == "https://i.ytimg.com/vi/abc/maxres.jpg"
    assert a.metadata_json["is_generated_transcript"] is False
    assert a.metadata_json["video_id"] == "abc123"


def test_map_video_to_article_no_thumbnails() -> None:
    info = {**_INFO, "thumbnails": []}
    a = map_video_to_article("v", info, "t", "en", False)
    assert a.hero_image_url is None


def test_map_video_to_article_thumbnail_string() -> None:
    info = {**_INFO, "thumbnails": None, "thumbnail": "https://i.ytimg.com/thumb.jpg"}
    a = map_video_to_article("v", info, "t", "en", False)
    assert a.hero_image_url == "https://i.ytimg.com/thumb.jpg"


def test_map_video_to_article_missing_title_uses_fallback() -> None:
    info = {**_INFO, "title": None}
    a = map_video_to_article("xyz", info, "t", "en", False)
    assert "xyz" in a.headline


def test_map_video_to_article_falls_back_to_uploader() -> None:
    info = {**_INFO, "channel": None, "uploader": "SomeUploader"}
    a = map_video_to_article("v", info, "t", "en", False)
    assert a.publisher == "SomeUploader"


# ---------------------------------------------------------------------------
# YouTubeConnector.fetch — search_fn + transcript API mocked
# ---------------------------------------------------------------------------

def _make_video(vid_id: str, upload_date: str = "20241210") -> dict:
    return {
        "id": vid_id,
        "title": f"Video {vid_id}",
        "channel": "TestChannel",
        "upload_date": upload_date,
        "description": "",
        "thumbnails": [],
    }


def _make_fetched(text: str = "transcript text", language: str = "en") -> MagicMock:
    snippet = MagicMock()
    snippet.text = text
    fetched = MagicMock()
    fetched.snippets = [snippet]
    fetched.language_code = language
    fetched.is_generated = False
    return fetched


@pytest.mark.asyncio
async def test_fetch_success(limiter: RedisRateLimiter) -> None:
    search_fn = MagicMock(return_value=[_make_video("v1")])
    api = MagicMock()
    api.fetch.return_value = _make_fetched("Great transcript")
    connector = _make_connector(limiter, search_fn=search_fn, transcript_api=api)

    articles = await connector.fetch("Tesla", SINCE)
    assert len(articles) == 1
    assert articles[0].external_id == "yt:v1"
    assert articles[0].raw_content == "Great transcript"


@pytest.mark.asyncio
async def test_fetch_skips_video_with_transcripts_disabled(
    limiter: RedisRateLimiter,
) -> None:
    from youtube_transcript_api import TranscriptsDisabled

    search_fn = MagicMock(return_value=[_make_video("v1"), _make_video("v2")])
    api = MagicMock()
    api.fetch.side_effect = [TranscriptsDisabled("v1"), _make_fetched("v2 transcript")]
    connector = _make_connector(limiter, search_fn=search_fn, transcript_api=api)

    articles = await connector.fetch("Tesla", SINCE)
    assert len(articles) == 1
    assert articles[0].external_id == "yt:v2"


@pytest.mark.asyncio
async def test_fetch_skips_no_transcript_found(limiter: RedisRateLimiter) -> None:
    from youtube_transcript_api import NoTranscriptFound

    search_fn = MagicMock(return_value=[_make_video("v1")])
    api = MagicMock()
    api.fetch.side_effect = NoTranscriptFound("v1", ["en"], [])
    connector = _make_connector(limiter, search_fn=search_fn, transcript_api=api)

    articles = await connector.fetch("Tesla", SINCE)
    assert articles == []


@pytest.mark.asyncio
async def test_fetch_skips_video_unavailable(limiter: RedisRateLimiter) -> None:
    from youtube_transcript_api import VideoUnavailable

    search_fn = MagicMock(return_value=[_make_video("v1")])
    api = MagicMock()
    api.fetch.side_effect = VideoUnavailable("v1")
    connector = _make_connector(limiter, search_fn=search_fn, transcript_api=api)

    articles = await connector.fetch("Tesla", SINCE)
    assert articles == []


@pytest.mark.asyncio
async def test_fetch_skips_empty_transcript(limiter: RedisRateLimiter) -> None:
    search_fn = MagicMock(return_value=[_make_video("v1")])
    fetched = MagicMock()
    fetched.snippets = [MagicMock(text="  ")]
    fetched.language_code = "en"
    fetched.is_generated = True
    api = MagicMock()
    api.fetch.return_value = fetched
    connector = _make_connector(limiter, search_fn=search_fn, transcript_api=api)

    articles = await connector.fetch("Tesla", SINCE)
    assert articles == []


@pytest.mark.asyncio
async def test_fetch_empty_search_results(limiter: RedisRateLimiter) -> None:
    search_fn = MagicMock(return_value=[])
    connector = _make_connector(limiter, search_fn=search_fn)

    articles = await connector.fetch("Tesla", SINCE)
    assert articles == []


@pytest.mark.asyncio
async def test_fetch_filters_old_videos(limiter: RedisRateLimiter) -> None:
    # upload_date 20200101 — before SINCE=2024-01-01
    old_vid = _make_video("v1", upload_date="20180101")
    search_fn = MagicMock(return_value=[old_vid])
    connector = _make_connector(limiter, search_fn=search_fn)

    articles = await connector.fetch("Tesla", since=datetime(2024, 1, 1, tzinfo=UTC))
    assert articles == []


@pytest.mark.asyncio
async def test_fetch_search_failure_raises_service_unavailable(
    limiter: RedisRateLimiter,
) -> None:
    search_fn = MagicMock(side_effect=RuntimeError("network error"))
    connector = _make_connector(limiter, search_fn=search_fn)

    with pytest.raises(ServiceUnavailableError, match="yt-dlp search failed"):
        await connector.fetch("Tesla", SINCE)


@pytest.mark.asyncio
async def test_fetch_records_failure_on_search_error(
    redis: fakeredis.FakeRedis, limiter: RedisRateLimiter
) -> None:
    search_fn = MagicMock(side_effect=RuntimeError("boom"))
    connector = _make_connector(limiter, search_fn=search_fn)

    with pytest.raises(ServiceUnavailableError):
        await connector.fetch("Tesla", SINCE)

    val = await redis.get(f"vt:cb:failures:{SOURCE_ID}")
    assert val is not None and int(val) >= 1


@pytest.mark.asyncio
async def test_fetch_mixed_batch_partial_transcripts(limiter: RedisRateLimiter) -> None:
    from youtube_transcript_api import TranscriptsDisabled

    search_fn = MagicMock(
        return_value=[_make_video("v1"), _make_video("v2"), _make_video("v3")]
    )
    api = MagicMock()
    api.fetch.side_effect = [
        _make_fetched("Transcript for v1"),
        TranscriptsDisabled("v2"),
        _make_fetched("Transcript for v3"),
    ]
    connector = _make_connector(limiter, search_fn=search_fn, transcript_api=api)

    articles = await connector.fetch("Tesla", SINCE)
    assert len(articles) == 2
    ids = {a.external_id for a in articles}
    assert "yt:v1" in ids and "yt:v3" in ids and "yt:v2" not in ids


@pytest.mark.asyncio
async def test_remaining_quota(limiter: RedisRateLimiter) -> None:
    connector = _make_connector(limiter)
    quota = await connector.remaining_quota()
    assert quota.source_id == SOURCE_ID
    assert quota.calls_made == 0

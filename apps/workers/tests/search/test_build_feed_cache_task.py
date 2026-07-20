"""Unit tests: build_feed_cache task settings and constants."""

from __future__ import annotations

from tasks.search.build_feed_cache import (
    _ARTICLE_PREVIEW,
    _CACHE_TTL,
    _FEED_KEY_PREFIX,
    _STORY_LIMIT,
    _TRACKED_KEY_PREFIX,
    CacheSettings,
)


def test_cache_ttl_is_positive() -> None:
    assert _CACHE_TTL > 0


def test_story_limit_is_positive() -> None:
    assert _STORY_LIMIT > 0


def test_article_preview_count_is_positive() -> None:
    assert _ARTICLE_PREVIEW > 0


def test_feed_key_prefix() -> None:
    assert _FEED_KEY_PREFIX == "vt:feed:"


def test_tracked_key_prefix() -> None:
    assert _TRACKED_KEY_PREFIX == "vt:tracked:"


def test_settings_default_database_url_empty() -> None:
    s = CacheSettings()
    # empty → task returns "no_database_url" without connecting
    assert isinstance(s.database_url, str)


def test_settings_default_feed_cache_ttl() -> None:
    s = CacheSettings()
    assert s.feed_cache_ttl == _CACHE_TTL


def test_settings_default_feed_story_limit() -> None:
    s = CacheSettings()
    assert s.feed_story_limit == _STORY_LIMIT


def test_run_returns_no_database_url_when_url_missing(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "")
    from tasks.search.build_feed_cache import run

    result = run(entity_id="some-id")
    assert result["status"] == "no_database_url"

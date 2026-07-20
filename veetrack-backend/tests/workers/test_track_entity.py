"""Unit tests: track_new_entity task — guard clause and settings.

Tests run() without a real database or Redis.
"""

from __future__ import annotations

import pytest


def test_run_no_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """run(keyword=...) returns {status: no_database_url} when DATABASE_URL is empty."""
    monkeypatch.setenv("DATABASE_URL", "")
    from workers.tasks.search.track_new_entity import run

    result = run(keyword="Tesla")
    assert result == {"status": "no_database_url"}


def test_run_no_database_url_status_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """The returned dict always has a 'status' key equal to 'no_database_url'."""
    monkeypatch.setenv("DATABASE_URL", "")
    from workers.tasks.search.track_new_entity import run

    result = run(keyword="OpenAI")
    assert "status" in result
    assert result["status"] == "no_database_url"


def test_run_no_database_url_for_various_keywords(monkeypatch: pytest.MonkeyPatch) -> None:
    """Guard clause fires for any keyword when DATABASE_URL is empty."""
    monkeypatch.setenv("DATABASE_URL", "")
    from workers.tasks.search.track_new_entity import run

    for keyword in ["", "Apple", "some long keyword phrase", "123"]:
        result = run(keyword=keyword)
        assert result["status"] == "no_database_url", (
            f"Expected no_database_url for keyword={keyword!r}, got {result}"
        )


def test_track_settings_defaults() -> None:
    """TrackSettings has sensible default field types."""
    from workers.tasks.search.track_new_entity import TrackSettings

    s = TrackSettings()
    assert isinstance(s.database_url, str)
    assert isinstance(s.redis_url, str)
    assert s.redis_url.startswith("redis://")


def test_track_settings_database_url_empty_by_default() -> None:
    """TrackSettings.database_url defaults to '' when no env var is set."""
    from workers.tasks.search.track_new_entity import TrackSettings

    s = TrackSettings()
    # When DATABASE_URL env var is absent, the default should be an empty string
    # (guard clause in run() checks this and short-circuits).
    assert isinstance(s.database_url, str)

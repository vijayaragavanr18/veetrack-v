"""Unit tests: track_new_entity task settings."""

from __future__ import annotations

from tasks.search.track_new_entity import TrackSettings


def test_settings_default_database_url_empty() -> None:
    s = TrackSettings()
    assert isinstance(s.database_url, str)


def test_settings_default_redis_url() -> None:
    s = TrackSettings()
    assert s.redis_url.startswith("redis://")


def test_run_returns_no_database_url_when_missing(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "")
    from tasks.search.track_new_entity import run

    result = run(keyword="tesla")
    assert result["status"] == "no_database_url"

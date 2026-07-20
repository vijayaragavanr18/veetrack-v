"""Unit tests: purge_old_articles task — guard clause only.

Tests that run() returns {"status": "no_database_url"} when DATABASE_URL
is empty, without touching a real database or Redis.
"""

from __future__ import annotations

import pytest


def test_purge_run_no_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """run() returns {status: no_database_url} when DATABASE_URL is empty."""
    monkeypatch.setenv("DATABASE_URL", "")
    from workers.tasks.system.purge_old_articles import run

    result = run()
    assert result == {"status": "no_database_url"}


def test_purge_run_no_database_url_status_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """The returned dict has a 'status' key when DATABASE_URL is empty."""
    monkeypatch.setenv("DATABASE_URL", "")
    from workers.tasks.system.purge_old_articles import run

    result = run()
    assert "status" in result
    assert result["status"] == "no_database_url"


def test_purge_settings_defaults() -> None:
    """PurgeSettings has expected default field types."""
    from workers.tasks.system.purge_old_articles import PurgeSettings

    s = PurgeSettings()
    assert isinstance(s.database_url, str)
    assert isinstance(s.redis_url, str)
    assert s.redis_url.startswith("redis://")

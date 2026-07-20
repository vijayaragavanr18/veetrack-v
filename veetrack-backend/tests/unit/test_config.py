"""Unit tests for Settings configuration loading."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def _make_settings(**kwargs: str) -> Settings:
    """Create a Settings instance with minimal valid env vars plus overrides."""
    defaults = {
        "database_url": "postgresql+asyncpg://u:p@localhost/db",
        "redis_url": "redis://localhost:6379/0",
        "jwt_secret": "a-valid-secret-that-is-long-enough",
        "environment": "test",
    }
    defaults.update(kwargs)
    return Settings(**defaults)  # type: ignore[arg-type]


def test_settings_loads_with_valid_values() -> None:
    """Settings succeeds when all required vars are present."""
    s = _make_settings()
    assert s.database_url.startswith("postgresql")
    assert s.redis_url.startswith("redis://")
    assert s.environment == "test"


def test_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """Optional fields have expected defaults when no env vars override them."""
    monkeypatch.delenv("NEWSDATA_API_KEY", raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    s = _make_settings()
    assert s.newsdata_api_key == ""
    assert s.log_level == "INFO"


def test_settings_rejects_placeholder_jwt_secret() -> None:
    """A placeholder JWT_SECRET value raises a validation error."""
    with pytest.raises(ValidationError, match="placeholder"):
        _make_settings(jwt_secret="changeme")


def test_settings_rejects_empty_jwt_secret() -> None:
    """An empty JWT_SECRET raises a validation error."""
    with pytest.raises(ValidationError):
        _make_settings(jwt_secret="")


def test_settings_rejects_missing_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing DATABASE_URL raises a validation error."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValidationError):
        Settings(  # type: ignore[call-arg]
            redis_url="redis://localhost",
            jwt_secret="valid-secret",
        )

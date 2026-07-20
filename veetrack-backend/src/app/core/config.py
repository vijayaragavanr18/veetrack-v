"""Application configuration via pydantic-settings.

Required variables (DATABASE_URL, REDIS_URL, JWT_SECRET) cause a hard failure
on startup if not set, with a clear error message — never silent defaults for secrets.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed configuration loaded from environment variables / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Runtime environment
    environment: Literal["development", "production", "test"] = "development"
    log_level: str = "INFO"
    api_version: str = "0.1.0"

    # Required: fail fast if missing in non-test environments
    database_url: str
    redis_url: str
    jwt_secret: str

    # Optional external API keys
    newsdata_api_key: str = ""
    twitterapi_io_key: str = ""
    anthropic_api_key: str = ""

    # Observability (optional — left empty disables)
    sentry_dsn: str = ""
    sentry_traces_sample_rate: float = 0.1  # 10% of transactions sampled
    prometheus_enabled: bool = True  # expose /metrics endpoint

    @field_validator("jwt_secret")
    @classmethod
    def jwt_secret_must_not_be_placeholder(cls, v: str) -> str:
        """Reject obvious placeholder values that would compromise security."""
        if v in {"changeme", "secret", "changeme-replace-with-a-long-random-secret", ""}:
            raise ValueError(
                "JWT_SECRET is set to a placeholder value. "
                "Set a strong random secret before running the application."
            )
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached application settings singleton."""
    return Settings()  # type: ignore[call-arg]  # values come from env

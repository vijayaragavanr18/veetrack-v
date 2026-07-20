"""System ping task — proves API → broker → worker → Redis round-trip works."""

from __future__ import annotations

from datetime import UTC, datetime

import redis as redis_sync
from tenacity import retry, stop_after_attempt, wait_exponential

from celery_app import app, worker_settings


@app.task(
    name="tasks.system.ping.run",
    queue="ingestion",
    bind=True,
    max_retries=3,
    default_retry_delay=2,
)
def run(self: object, *, redis_key: str) -> str:  # type: ignore[misc]
    """Write a UTC timestamp to redis_key; return the timestamp string.

    The API polls this key to confirm the round-trip completed.
    """
    timestamp = _write_ping(redis_key)
    return timestamp


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
def _write_ping(redis_key: str) -> str:
    timestamp = datetime.now(UTC).isoformat()
    client = redis_sync.from_url(worker_settings.redis_url, decode_responses=True)
    client.set(redis_key, timestamp, ex=30)
    return timestamp

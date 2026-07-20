"""Tests for the system ping task.

Runs with CELERY_TASK_ALWAYS_EAGER=True so no broker is needed for unit tests.
The integration test that needs a real broker is in apps/api/tests/integration/.
"""

from __future__ import annotations

import os

import fakeredis

# Set env before any app import
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")


def test_ping_task_writes_timestamp_to_redis() -> None:
    """The ping task writes an ISO timestamp to the given Redis key."""
    fake = fakeredis.FakeRedis(decode_responses=True)

    # Patch redis.from_url to return our fake client
    import unittest.mock as mock

    import workers.tasks.system.ping as ping_mod

    with mock.patch("workers.tasks.system.ping.redis_sync.from_url", return_value=fake):
        result = ping_mod._write_ping("test:ping:123")

    assert isinstance(result, str)
    assert "T" in result  # ISO format contains 'T' between date and time
    stored = fake.get("test:ping:123")
    assert stored == result


def test_ping_task_runs_eagerly() -> None:
    """With task_always_eager, run() executes synchronously and returns a timestamp."""
    import unittest.mock as mock

    import workers.tasks.system.ping as ping_mod
    from workers.celery_app import app

    fake = fakeredis.FakeRedis(decode_responses=True)

    with mock.patch("workers.tasks.system.ping.redis_sync.from_url", return_value=fake):
        app.conf.task_always_eager = True
        try:
            result = ping_mod.run.apply(kwargs={"redis_key": "eager:ping:key"}).get()
        finally:
            app.conf.task_always_eager = False

    assert isinstance(result, str)
    assert fake.get("eager:ping:key") == result


def test_ping_task_retries_on_redis_error() -> None:
    """_write_ping retries via tenacity on connection errors."""
    import unittest.mock as mock

    import workers.tasks.system.ping as ping_mod

    call_count = 0
    real_fake = fakeredis.FakeRedis(decode_responses=True)

    def flaky_from_url(url: str, **kwargs: object) -> fakeredis.FakeRedis:
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ConnectionError("simulated redis error")
        return real_fake

    with mock.patch("workers.tasks.system.ping.redis_sync.from_url", side_effect=flaky_from_url):
        result = ping_mod._write_ping("retry:ping:key")

    assert call_count == 3
    assert real_fake.get("retry:ping:key") == result

"""Unit tests for PingWorker use case — no real Redis or Celery required."""

from __future__ import annotations

import pytest

from app.application.use_cases.ping_worker import PING_KEY_PREFIX, PingWorker
from tests.conftest import FakeCacheGateway


class FakeDispatcher:
    """Records dispatched tasks and immediately writes the ping value to the fake cache."""

    def __init__(self, cache: FakeCacheGateway) -> None:
        self._cache = cache
        self.calls: list[dict[str, object]] = []

    def send(
        self,
        task_name: str,
        *,
        args: tuple[object, ...] = (),
        kwargs: dict[str, object] | None = None,
        queue: str | None = None,
    ) -> str:
        self.calls.append({"task_name": task_name, "kwargs": kwargs, "queue": queue})
        # Simulate a synchronous worker: write the ping result immediately
        import asyncio
        from datetime import UTC, datetime

        redis_key = (kwargs or {}).get("redis_key", "")
        if isinstance(redis_key, str) and redis_key:
            timestamp = datetime.now(UTC).isoformat().encode()
            # Run in an event loop to set the value synchronously
            asyncio.get_event_loop().run_until_complete(self._cache.set(redis_key, timestamp))
        return "fake-task-id"


@pytest.mark.asyncio
async def test_ping_worker_ok() -> None:
    """PingWorker returns status=ok when the dispatcher writes to cache."""
    from datetime import UTC, datetime

    cache = FakeCacheGateway(available=True)

    class ImmediateDispatcher:
        def send(
            self,
            task_name: str,
            *,
            args: tuple[object, ...] = (),
            kwargs: dict[str, object] | None = None,
            queue: str | None = None,
        ) -> str:
            redis_key = (kwargs or {}).get("redis_key", "")
            if isinstance(redis_key, str) and redis_key:
                # Write directly to the in-memory store — no event loop nesting needed.
                cache._store[redis_key] = datetime.now(UTC).isoformat().encode()
            return "task-123"

    use_case = PingWorker(cache=cache, dispatcher=ImmediateDispatcher())  # type: ignore[arg-type]
    result = await use_case.execute()

    assert result.status == "ok"
    assert result.task_id == "task-123"
    assert result.latency_ms is not None
    assert result.worker_timestamp is not None
    assert result.redis_key.startswith(PING_KEY_PREFIX)


@pytest.mark.asyncio
async def test_ping_worker_timeout_when_no_worker() -> None:
    """PingWorker returns status=timeout when no worker writes to Redis."""
    import app.application.use_cases.ping_worker as uc_mod

    original_timeout = uc_mod.POLL_TIMEOUT
    original_interval = uc_mod.POLL_INTERVAL
    # Speed up the test: 0.1 s timeout, 0.02 s poll interval
    uc_mod.POLL_TIMEOUT = 0.1
    uc_mod.POLL_INTERVAL = 0.02

    try:
        cache = FakeCacheGateway(available=True)

        class NoOpDispatcher:
            def send(
                self,
                task_name: str,
                *,
                args: tuple[object, ...] = (),
                kwargs: dict[str, object] | None = None,
                queue: str | None = None,
            ) -> str:
                return "no-worker-task"

        use_case = PingWorker(cache=cache, dispatcher=NoOpDispatcher())  # type: ignore[arg-type]
        result = await use_case.execute()
    finally:
        uc_mod.POLL_TIMEOUT = original_timeout
        uc_mod.POLL_INTERVAL = original_interval

    assert result.status == "timeout"
    assert result.task_id == "no-worker-task"
    assert result.worker_timestamp is None

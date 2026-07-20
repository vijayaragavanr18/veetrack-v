"""Use case: dispatch a ping task to a Celery worker and verify the round-trip via Redis."""

from __future__ import annotations

import asyncio
import time
import uuid

from app.application.dto.system import PingWorkerResponse
from app.domain.interfaces.services import CacheGateway, TaskDispatcher

PING_TASK_NAME = "tasks.system.ping.run"
PING_KEY_PREFIX = "system:ping:"
PING_TTL = 30  # seconds — well above any reasonable local worker latency
POLL_INTERVAL = 0.05  # 50 ms
POLL_TIMEOUT = 10.0  # give up after 10 s


class PingWorker:
    """Dispatch a ping task and poll Redis until the worker writes its result."""

    def __init__(self, cache: CacheGateway, dispatcher: TaskDispatcher) -> None:
        self._cache = cache
        self._dispatcher = dispatcher

    async def execute(self) -> PingWorkerResponse:
        ping_id = str(uuid.uuid4())
        redis_key = f"{PING_KEY_PREFIX}{ping_id}"

        task_id = self._dispatcher.send(
            PING_TASK_NAME,
            kwargs={"redis_key": redis_key},
            queue="ingestion",  # use ingestion queue — always running in the base worker config
        )

        start = time.monotonic()
        deadline = start + POLL_TIMEOUT
        worker_timestamp: str | None = None

        while time.monotonic() < deadline:
            raw = await self._cache.get(redis_key)
            if raw is not None:
                worker_timestamp = raw.decode()
                break
            await asyncio.sleep(POLL_INTERVAL)

        elapsed_ms = (time.monotonic() - start) * 1000

        if worker_timestamp is None:
            return PingWorkerResponse(
                task_id=task_id,
                redis_key=redis_key,
                status="timeout",
                latency_ms=round(elapsed_ms, 1),
            )

        return PingWorkerResponse(
            task_id=task_id,
            redis_key=redis_key,
            status="ok",
            latency_ms=round(elapsed_ms, 1),
            worker_timestamp=worker_timestamp,
        )

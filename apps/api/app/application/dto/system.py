from __future__ import annotations

from pydantic import BaseModel


class PingWorkerResponse(BaseModel):
    task_id: str
    redis_key: str
    status: str
    latency_ms: float | None = None
    worker_timestamp: str | None = None

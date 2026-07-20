"""System / ops endpoints.

Routes:
  POST /api/v1/system/ping-worker — dispatch a ping task; poll Redis for round-trip result.
"""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends

from app.application.dto.system import PingWorkerResponse
from app.application.use_cases.ping_worker import PingWorker
from app.core.container import get_ping_worker_use_case

router = APIRouter(prefix="/system", tags=["system"])
logger = structlog.get_logger(__name__)


@router.post(
    "/ping-worker",
    response_model=PingWorkerResponse,
    summary="Ping Celery worker via Redis",
)
async def ping_worker(
    use_case: Annotated[PingWorker, Depends(get_ping_worker_use_case)],
) -> PingWorkerResponse:
    """Dispatch a lightweight ping task to the ingestion queue and return the round-trip result.

    - **status: ok** — worker received the task and wrote to Redis within the timeout.
    - **status: timeout** — no worker responded within ~10 s (workers not running).
    """
    result = await use_case.execute()
    logger.info("system.ping_worker", status=result.status, latency_ms=result.latency_ms)
    return result

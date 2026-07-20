"""Celery-backed implementation of TaskDispatcher.

The API uses this to enqueue tasks into the worker broker without importing
any Celery task functions — those live in apps/workers and are never imported
here.  We call send_task() by name, which is the standard Celery pattern for
cross-app dispatch.
"""

from __future__ import annotations

from typing import Any

import structlog
from celery import Celery

from app.domain.interfaces.services import TaskDispatcher

logger = structlog.get_logger(__name__)


class CeleryTaskDispatcher:
    """Dispatches tasks to the Celery broker by task name (no local task import)."""

    def __init__(self, celery_app: Celery) -> None:
        self._app = celery_app

    def send(
        self,
        task_name: str,
        *,
        args: tuple[Any, ...] = (),
        kwargs: dict[str, Any] | None = None,
        queue: str | None = None,
    ) -> str:
        """Enqueue a named Celery task; return the task_id."""
        result = self._app.send_task(
            task_name,
            args=args,
            kwargs=kwargs or {},
            queue=queue,
        )
        task_id: str = result.id
        logger.info("task.dispatched", task_name=task_name, task_id=task_id, queue=queue)
        return task_id


# Static Protocol assertion — fails at import time if CeleryTaskDispatcher drifts from protocol.
_: TaskDispatcher = CeleryTaskDispatcher.__new__(CeleryTaskDispatcher)

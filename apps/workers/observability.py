"""Worker observability — Sentry + Prometheus Celery signals.

Import this module once in celery_app.py to wire up all signals.
Purely additive — no task logic is altered.
"""

from __future__ import annotations

import logging
import os
import time

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prometheus metrics (optional — skip gracefully if prometheus_client absent)
# ---------------------------------------------------------------------------

try:
    from prometheus_client import Counter, Histogram, start_http_server as _start_http

    _task_started = Counter(
        "celery_tasks_started_total",
        "Total Celery tasks started",
        ["task_name", "queue"],
    )
    _task_succeeded = Counter(
        "celery_tasks_succeeded_total",
        "Total Celery tasks succeeded",
        ["task_name", "queue"],
    )
    _task_failed = Counter(
        "celery_tasks_failed_total",
        "Total Celery tasks failed",
        ["task_name", "queue"],
    )
    _task_duration = Histogram(
        "celery_task_duration_seconds",
        "Celery task execution duration",
        ["task_name", "queue"],
        buckets=[0.1, 0.5, 1, 5, 10, 30, 60, 120],
    )
    _PROMETHEUS_AVAILABLE = True
except ImportError:
    _PROMETHEUS_AVAILABLE = False
    logger.warning("observability.prometheus_unavailable")

# Per-task start timestamps stored by task id
_task_start_times: dict[str, float] = {}


def _queue_for(task_name: str) -> str:
    """Best-effort queue name extraction from task name."""
    parts = task_name.split(".")
    return parts[1] if len(parts) > 1 else "default"


# ---------------------------------------------------------------------------
# Sentry for workers
# ---------------------------------------------------------------------------


def init_worker_sentry() -> None:
    """Initialise Sentry in the worker process if SENTRY_DSN is set."""
    dsn = os.environ.get("SENTRY_DSN", "")
    if not dsn:
        return
    try:
        import sentry_sdk
        from sentry_sdk.integrations.celery import CeleryIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration
        import logging as _logging

        environment = os.environ.get("ENVIRONMENT", "development")
        sentry_sdk.init(
            dsn=dsn,
            environment=environment,
            integrations=[
                CeleryIntegration(monitor_beat_tasks=True),
                LoggingIntegration(level=_logging.WARNING, event_level=_logging.ERROR),
            ],
            send_default_pii=False,
        )
        logger.info("observability.worker_sentry_initialized", environment=environment)
    except ImportError:
        logger.warning("observability.sentry_unavailable")


# ---------------------------------------------------------------------------
# Signal registration
# ---------------------------------------------------------------------------


def register_celery_signals(app: object) -> None:
    """Wire Celery signals onto *app* for metrics + Sentry breadcrumbs.

    Call once after the Celery app is created in celery_app.py.
    """
    from celery import signals

    @signals.task_prerun.connect
    def on_task_prerun(task_id: str, task: object, **kwargs: object) -> None:
        _task_start_times[task_id] = time.monotonic()
        if _PROMETHEUS_AVAILABLE:
            _task_started.labels(
                task_name=task.name,  # type: ignore[attr-defined]
                queue=_queue_for(task.name),  # type: ignore[attr-defined]
            ).inc()

    @signals.task_postrun.connect
    def on_task_postrun(
        task_id: str, task: object, retval: object, state: str, **kwargs: object
    ) -> None:
        start = _task_start_times.pop(task_id, None)
        if start is not None and _PROMETHEUS_AVAILABLE:
            duration = time.monotonic() - start
            queue = _queue_for(task.name)  # type: ignore[attr-defined]
            _task_duration.labels(task_name=task.name, queue=queue).observe(duration)  # type: ignore[attr-defined]
            if state == "SUCCESS":
                _task_succeeded.labels(task_name=task.name, queue=queue).inc()  # type: ignore[attr-defined]
            else:
                _task_failed.labels(task_name=task.name, queue=queue).inc()  # type: ignore[attr-defined]

    @signals.task_failure.connect
    def on_task_failure(
        task_id: str, exception: Exception, task: object, **kwargs: object
    ) -> None:
        """Capture unhandled task exceptions into Sentry."""
        try:
            import sentry_sdk
            sentry_sdk.capture_exception(exception)
        except ImportError:
            pass
        logger.error(
            "task.failed",
            task_id=task_id,
            exc_type=type(exception).__name__,
            error=str(exception),
        )

    logger.debug("observability.celery_signals_registered")

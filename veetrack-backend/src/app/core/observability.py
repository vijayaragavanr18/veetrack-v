"""Observability bootstrap — Sentry + Prometheus.

Called once from main.py's create_app().  Purely additive; no business logic
return values or behaviours are altered.
"""

from __future__ import annotations

import structlog
from fastapi import FastAPI

logger = structlog.get_logger(__name__)


def init_sentry(dsn: str, environment: str, traces_sample_rate: float) -> None:
    """Initialise Sentry SDK if a DSN is configured.  No-op if dsn is empty."""
    if not dsn:
        logger.debug("observability.sentry_disabled")
        return
    import logging

    import sentry_sdk
    from sentry_sdk.integrations.asyncio import AsyncioIntegration
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.logging import LoggingIntegration
    from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        traces_sample_rate=traces_sample_rate,
        integrations=[
            FastApiIntegration(transaction_style="endpoint"),
            SqlalchemyIntegration(),
            AsyncioIntegration(),
            LoggingIntegration(level=logging.WARNING, event_level=logging.ERROR),
        ],
        send_default_pii=False,
    )
    logger.info("observability.sentry_initialized", environment=environment)


def mount_prometheus(app: FastAPI) -> None:
    """Attach prometheus-fastapi-instrumentator to *app*.

    Exposes GET /metrics (Prometheus text format).
    Instruments: request count, latency histogram by method/path/status.
    """
    from prometheus_fastapi_instrumentator import Instrumentator

    instrumentator = Instrumentator(
        should_group_status_codes=False,
        excluded_handlers=["/metrics", "/health", "/api/v1/health"],
    )
    instrumentator.instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)
    logger.info("observability.prometheus_mounted", endpoint="/metrics")

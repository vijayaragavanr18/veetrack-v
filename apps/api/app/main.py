"""FastAPI application factory.

Creates and configures the app with:
  - Structured logging (structlog)
  - Request ID + timing middleware
  - Centralized domain exception handlers
  - Versioned v1 router
"""

from __future__ import annotations

import structlog
from fastapi import FastAPI

from app.api.v1.router import v1_router
from app.core.config import get_settings
from app.core.error_handlers import register_error_handlers
from app.core.middleware import RequestIDMiddleware, RequestLoggingMiddleware
from app.core.observability import init_sentry, mount_prometheus
from app.infrastructure.logging.setup import configure_logging

# Bootstrap logging before anything else
settings = get_settings()
configure_logging(environment=settings.environment, log_level=settings.log_level)

# Sentry is process-global — init once before the app is constructed
init_sentry(
    dsn=settings.sentry_dsn,
    environment=settings.environment,
    traces_sample_rate=settings.sentry_traces_sample_rate,
)

logger = structlog.get_logger(__name__)


def create_app() -> FastAPI:
    """Construct the FastAPI application and register all components."""
    app = FastAPI(
        title="VeeTrack API",
        version=settings.api_version,
        description="AI-powered media intelligence platform",
        docs_url="/docs" if settings.environment != "production" else None,
        redoc_url="/redoc" if settings.environment != "production" else None,
    )

    # Middleware — outermost first (RequestID must precede logging so request_id is bound)
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(RequestIDMiddleware)

    # Exception handlers
    register_error_handlers(app)

    # Prometheus metrics — expose /metrics before routers so it's registered first
    if settings.prometheus_enabled:
        mount_prometheus(app)

    # Routers
    app.include_router(v1_router)

    logger.info(
        "app.started",
        version=settings.api_version,
        environment=settings.environment,
    )
    return app


app = create_app()

"""Centralized exception handlers that map domain exceptions to HTTP responses.

Register all handlers by calling register_error_handlers(app) in main.py.
The client always receives a safe, structured JSON error body — never a raw
Python traceback.
"""

from __future__ import annotations

import traceback

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.v1.admin.dashboard import record_api_error
from app.domain.exceptions import (
    ConflictError,
    DomainError,
    ForbiddenError,
    NotFoundError,
    ServiceUnavailableError,
    UnauthorizedError,
    ValidationError,
)

logger = structlog.get_logger(__name__)


def _error_body(code: str, message: str) -> dict[str, str]:
    return {"error": code, "message": message}


def register_error_handlers(app: FastAPI) -> None:
    """Attach all domain-to-HTTP exception handlers to the FastAPI app."""

    @app.exception_handler(NotFoundError)
    async def handle_not_found(request: Request, exc: NotFoundError) -> JSONResponse:
        logger.info("error.not_found", path=request.url.path, detail=exc.message)
        return JSONResponse(
            status_code=404,
            content=_error_body("NOT_FOUND", exc.message),
        )

    @app.exception_handler(ConflictError)
    async def handle_conflict(request: Request, exc: ConflictError) -> JSONResponse:
        logger.info("error.conflict", path=request.url.path, detail=exc.message)
        return JSONResponse(
            status_code=409,
            content=_error_body("CONFLICT", exc.message),
        )

    @app.exception_handler(ValidationError)
    async def handle_validation(request: Request, exc: ValidationError) -> JSONResponse:
        logger.info("error.validation", path=request.url.path, detail=exc.message)
        return JSONResponse(
            status_code=422,
            content=_error_body("VALIDATION_ERROR", exc.message),
        )

    @app.exception_handler(UnauthorizedError)
    async def handle_unauthorized(request: Request, exc: UnauthorizedError) -> JSONResponse:
        logger.info("error.unauthorized", path=request.url.path)
        return JSONResponse(
            status_code=401,
            content=_error_body("UNAUTHORIZED", exc.message),
            headers={"WWW-Authenticate": "Bearer"},
        )

    @app.exception_handler(ForbiddenError)
    async def handle_forbidden(request: Request, exc: ForbiddenError) -> JSONResponse:
        logger.info("error.forbidden", path=request.url.path, detail=exc.message)
        return JSONResponse(
            status_code=403,
            content=_error_body("FORBIDDEN", exc.message),
        )

    @app.exception_handler(ServiceUnavailableError)
    async def handle_service_unavailable(
        request: Request, exc: ServiceUnavailableError
    ) -> JSONResponse:
        logger.warning("error.service_unavailable", path=request.url.path, detail=exc.message)
        return JSONResponse(
            status_code=503,
            content=_error_body("SERVICE_UNAVAILABLE", exc.message),
        )

    @app.exception_handler(DomainError)
    async def handle_generic_domain(request: Request, exc: DomainError) -> JSONResponse:
        """Catch-all for any DomainError subclass not handled above."""
        logger.error("error.domain_unhandled", path=request.url.path, detail=exc.message)
        return JSONResponse(
            status_code=500,
            content=_error_body("INTERNAL_ERROR", "An unexpected error occurred."),
        )

    @app.exception_handler(Exception)
    async def handle_unhandled(request: Request, exc: Exception) -> JSONResponse:
        """Last-resort handler for unhandled exceptions — logs full traceback."""
        logger.error(
            "error.unhandled",
            path=request.url.path,
            exc_type=type(exc).__name__,
            traceback=traceback.format_exc(),
        )
        record_api_error()
        return JSONResponse(
            status_code=500,
            content=_error_body("INTERNAL_ERROR", "An unexpected error occurred."),
        )

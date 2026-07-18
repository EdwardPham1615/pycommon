"""RFC 9457 Problem Details models and exception handlers."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from pycommon.errors import AppError
from pycommon.logging import get_logger

logger = get_logger(__name__)


class ProblemDetail(BaseModel):
    """RFC 9457 Problem Details for HTTP APIs."""

    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None
    errors: list[dict[str, Any]] | None = None


def problem_response(
    *,
    title: str,
    status_code: int,
    detail: str | None = None,
    instance: str | None = None,
    type_: str = "about:blank",
    errors: list[dict[str, Any]] | None = None,
) -> JSONResponse:
    body = ProblemDetail(
        type=type_,
        title=title,
        status=status_code,
        detail=detail,
        instance=instance,
        errors=errors,
    )
    return JSONResponse(
        status_code=status_code,
        content=body.model_dump(exclude_none=True),
        media_type="application/problem+json",
    )


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """Translate a domain :class:`AppError` into a Problem Details response."""
    if exc.status_code >= 500:
        logger.exception("app_error", path=request.url.path, title=exc.title)
    return problem_response(
        title=exc.title,
        status_code=exc.status_code,
        detail=exc.detail,
        instance=str(request.url.path),
        type_=exc.type_,
        errors=exc.errors,
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # Once a handler is registered for Exception, Starlette no longer logs the
    # traceback itself — do it here or 500s become invisible.
    logger.exception(
        "unhandled_exception",
        path=request.url.path,
        method=request.method,
        error=str(exc),
    )
    return problem_response(
        title="Internal Server Error",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="An unexpected error occurred",
        instance=str(request.url.path),
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register standard handlers: AppError -> Problem Details, Exception -> logged 500."""
    app.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_exception_handler)

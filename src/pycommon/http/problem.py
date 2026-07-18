"""RFC 9457 Problem Details models, handlers, and problem-type docs router."""

from __future__ import annotations

import time
from html import escape
from typing import Any

from fastapi import APIRouter, FastAPI, Request, status
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from pycommon.errors import (
    PROBLEM_TYPES,
    AppError,
    ErrorCode,
    problem_type_uri,
)
from pycommon.logging import get_logger

logger = get_logger(__name__)

_APP_STATE_PROBLEM_TYPE_BASE_URL = "problem_type_base_url"


class ProblemDetail(BaseModel):
    """RFC 9457 Problem Details for HTTP APIs.

    Extension members: ``error_code``, ``request_id``, ``server_time``.
    """

    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None
    errors: list[dict[str, Any]] | None = None
    error_code: int | None = None
    request_id: str | None = None
    server_time: int = Field(default_factory=lambda: int(time.time()))


def problem_response(
    *,
    title: str,
    status_code: int,
    detail: str | None = None,
    instance: str | None = None,
    type_: str = "about:blank",
    errors: list[dict[str, Any]] | None = None,
    error_code: int | None = None,
    request_id: str | None = None,
    server_time: int | None = None,
) -> JSONResponse:
    body = ProblemDetail(
        type=type_,
        title=title,
        status=status_code,
        detail=detail,
        instance=instance,
        errors=errors,
        error_code=error_code,
        request_id=request_id,
        server_time=server_time if server_time is not None else int(time.time()),
    )
    return JSONResponse(
        status_code=status_code,
        content=body.model_dump(exclude_none=True),
        media_type="application/problem+json",
    )


def _problem_type_base_url(request: Request) -> str | None:
    value = getattr(request.app.state, _APP_STATE_PROBLEM_TYPE_BASE_URL, None)
    return value if isinstance(value, str) else None


def _request_id(request: Request) -> str | None:
    value = getattr(request.state, "request_id", None)
    return value if isinstance(value, str) else None


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """Translate a domain :class:`AppError` into a Problem Details response."""
    if exc.status_code >= 500:
        logger.exception("app_error", path=request.url.path, title=exc.title)
    base_url = _problem_type_base_url(request)
    return problem_response(
        title=exc.title,
        status_code=exc.status_code,
        detail=exc.detail,
        instance=str(request.url.path),
        type_=exc.resolve_type(base_url=base_url),
        errors=exc.errors,
        error_code=int(exc.error_code),
        request_id=_request_id(request),
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
    base_url = _problem_type_base_url(request)
    return problem_response(
        title="Server Error",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="An unexpected error occurred",
        instance=str(request.url.path),
        type_=problem_type_uri(ErrorCode.SERVER, base_url=base_url),
        error_code=int(ErrorCode.SERVER),
        request_id=_request_id(request),
    )


def register_exception_handlers(
    app: FastAPI,
    *,
    problem_type_base_url: str | None = None,
) -> None:
    """Register standard handlers: AppError -> Problem Details, Exception -> logged 500.

    ``problem_type_base_url`` prefixes RFC 9457 ``type`` URIs (e.g.
    ``https://docs.example.com/problems``). When omitted, path-absolute URIs
    like ``/problems/input`` are used.
    """
    setattr(app.state, _APP_STATE_PROBLEM_TYPE_BASE_URL, problem_type_base_url)
    app.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_exception_handler)


def _problem_type_html(slug: str, *, base_url: str | None = None) -> str | None:
    for problem in PROBLEM_TYPES.values():
        if problem.slug == slug:
            type_uri = problem_type_uri(problem.code, base_url=base_url)
            return (
                "<!DOCTYPE html>\n"
                f"<html lang=\"en\"><head><meta charset=\"utf-8\">"
                f"<title>{escape(problem.title)}</title></head><body>\n"
                f"<h1>{escape(problem.title)}</h1>\n"
                f"<p><strong>type:</strong> <code>{escape(type_uri)}</code></p>\n"
                f"<p><strong>error_code:</strong> {int(problem.code)}</p>\n"
                f"<p><strong>default HTTP status:</strong> {problem.default_status}</p>\n"
                f"<p>{escape(problem.description)}</p>\n"
                "<p><a href=\"/problems\">All problem types</a></p>\n"
                "</body></html>\n"
            )
    return None


def _problem_index_html(*, base_url: str | None = None) -> str:
    items = []
    for problem in PROBLEM_TYPES.values():
        type_uri = problem_type_uri(problem.code, base_url=base_url)
        items.append(
            "<li>"
            f"<a href=\"/problems/{escape(problem.slug)}\">{escape(problem.title)}</a>"
            f" — <code>{escape(type_uri)}</code>"
            f" (error_code={int(problem.code)})"
            "</li>"
        )
    return (
        "<!DOCTYPE html>\n"
        "<html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<title>Problem Types</title></head><body>\n"
        "<h1>Problem Types</h1>\n"
        "<p>RFC 9457 problem type documentation for this API.</p>\n"
        f"<ul>\n{''.join(items)}\n</ul>\n"
        "</body></html>\n"
    )


def build_problem_types_router(*, problem_type_base_url: str | None = None) -> APIRouter:
    """Serve human-readable HTML docs so relative ``type`` URIs are dereferenceable."""
    router = APIRouter(tags=["problems"])

    @router.get("/problems", response_class=HTMLResponse, include_in_schema=False)
    async def problem_index() -> HTMLResponse:
        return HTMLResponse(_problem_index_html(base_url=problem_type_base_url))

    @router.get("/problems/{slug}", response_class=HTMLResponse, include_in_schema=False)
    async def problem_detail(slug: str) -> HTMLResponse:
        html = _problem_type_html(slug, base_url=problem_type_base_url)
        if html is None:
            return HTMLResponse(
                "<!DOCTYPE html><html><body><h1>Unknown problem type</h1></body></html>",
                status_code=404,
            )
        return HTMLResponse(html)

    return router

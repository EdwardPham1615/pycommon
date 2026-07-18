"""HTTP helpers: RFC 9457 Problem Details, pagination envelope."""

from __future__ import annotations

from typing import Any

from fastapi import Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field


class ProblemDetail(BaseModel):
    """RFC 9457 Problem Details for HTTP APIs."""

    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None
    errors: list[dict[str, Any]] | None = None


class PageMeta(BaseModel):
    next_cursor: str | None = None
    prev_cursor: str | None = None
    has_more: bool = False
    limit: int = 20


class Page[T](BaseModel):
    items: list[T]
    meta: PageMeta = Field(default_factory=PageMeta)


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


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    _ = exc
    return problem_response(
        title="Internal Server Error",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="An unexpected error occurred",
        instance=str(request.url.path),
    )

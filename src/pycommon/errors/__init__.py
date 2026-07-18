"""Shared application exception hierarchy.

Services raise these from domain/application code; the FastAPI handlers in
``pycommon.http`` translate them into RFC 9457 Problem Details responses.
"""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    """Base class for application errors that map to an HTTP status."""

    status_code: int = 500
    title: str = "Internal Server Error"
    type_: str = "about:blank"

    def __init__(
        self,
        detail: str | None = None,
        *,
        errors: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(detail or self.title)
        self.detail = detail
        self.errors = errors


class BadRequestError(AppError):
    status_code = 400
    title = "Bad Request"


class UnauthorizedError(AppError):
    status_code = 401
    title = "Unauthorized"


class ForbiddenError(AppError):
    status_code = 403
    title = "Forbidden"


class NotFoundError(AppError):
    status_code = 404
    title = "Not Found"


class ConflictError(AppError):
    status_code = 409
    title = "Conflict"


class UnprocessableEntityError(AppError):
    status_code = 422
    title = "Unprocessable Entity"


class TooManyRequestsError(AppError):
    status_code = 429
    title = "Too Many Requests"


class ServiceUnavailableError(AppError):
    status_code = 503
    title = "Service Unavailable"


__all__ = [
    "AppError",
    "BadRequestError",
    "ConflictError",
    "ForbiddenError",
    "NotFoundError",
    "ServiceUnavailableError",
    "TooManyRequestsError",
    "UnauthorizedError",
    "UnprocessableEntityError",
]

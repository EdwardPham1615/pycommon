"""Shared application errors and RFC 9457 problem-type registry.

Services raise :class:`AppError` from domain/application code; the FastAPI
handlers in ``pycommon.http`` translate them into Problem Details responses
with a stable ``type`` URI and an ``error_code`` extension.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Any, Self


class ErrorCode(IntEnum):
    """Application-level error codes shared across services."""

    OK = 0
    SERVER = 1
    DATABASE = 2
    INPUT = 3
    AUTH = 4
    APP_CHECK = 5


@dataclass(frozen=True, slots=True)
class ProblemType:
    """Canonical RFC 9457 problem-type metadata for an :class:`ErrorCode`."""

    code: ErrorCode
    slug: str
    title: str
    status_code: int
    description: str


PROBLEM_TYPES: dict[ErrorCode, ProblemType] = {
    ErrorCode.SERVER: ProblemType(
        code=ErrorCode.SERVER,
        slug="server",
        title="Server Error",
        status_code=500,
        description=(
            "An unexpected failure occurred while processing the request. "
            "Retry may help for transient faults; otherwise contact support with the request ID."
        ),
    ),
    ErrorCode.DATABASE: ProblemType(
        code=ErrorCode.DATABASE,
        slug="database",
        title="Database Error",
        status_code=500,
        description=(
            "A persistence-layer failure prevented completing the operation. "
            "The request was not fully applied; retry only if the operation is idempotent."
        ),
    ),
    ErrorCode.INPUT: ProblemType(
        code=ErrorCode.INPUT,
        slug="input",
        title="Input Error",
        status_code=400,
        description=(
            "The request was rejected because of invalid, missing, or conflicting input. "
            "Fix the request parameters or body and try again."
        ),
    ),
    ErrorCode.AUTH: ProblemType(
        code=ErrorCode.AUTH,
        slug="authorization",
        title="Authorization Error",
        status_code=401,
        description=(
            "Authentication or authorization failed. "
            "Provide a valid credential (or a credential with the required permissions) and retry."
        ),
    ),
    ErrorCode.APP_CHECK: ProblemType(
        code=ErrorCode.APP_CHECK,
        slug="app-check",
        title="App Check Error",
        status_code=403,
        description=(
            "The client failed an application integrity or device attestation check. "
            "Ensure the client is a genuine build of the official app and retry."
        ),
    ),
}


def problem_type_uri(code: ErrorCode, *, base_url: str | None = None) -> str:
    """Resolve the RFC 9457 ``type`` URI for an application error code.

    With no ``base_url``, returns a path-absolute URI (``/problems/{slug}``)
    that resolves against the API host. With ``base_url``, returns an absolute
    URI under that prefix (e.g. a public docs portal).
    """
    if code is ErrorCode.OK:
        raise ValueError("ErrorCode.OK has no problem type URI")
    problem = PROBLEM_TYPES[code]
    if base_url:
        return f"{base_url.rstrip('/')}/{problem.slug}"
    return f"/problems/{problem.slug}"


class AppError(Exception):
    """Application error with a fixed HTTP status derived from :class:`ErrorCode`."""

    def __init__(
        self,
        detail: str | None = None,
        *,
        error_code: ErrorCode = ErrorCode.SERVER,
        title: str | None = None,
        type_: str | None = None,
        errors: list[dict[str, Any]] | None = None,
    ) -> None:
        problem = PROBLEM_TYPES.get(error_code)
        self.error_code = error_code
        self.status_code = problem.status_code if problem is not None else 500
        if title is not None:
            self.title = title
        elif problem is not None:
            self.title = problem.title
        else:
            self.title = "Server Error"
        self.type_ = type_
        self.detail = detail
        self.errors = errors
        super().__init__(detail or self.title)

    def resolve_type(self, *, base_url: str | None = None) -> str:
        """Return the Problem Details ``type`` URI for this error."""
        if self.type_ is not None:
            return self.type_
        if self.error_code is ErrorCode.OK:
            return "about:blank"
        return problem_type_uri(self.error_code, base_url=base_url)

    @classmethod
    def server(
        cls,
        detail: str | None = None,
        *,
        title: str | None = None,
        type_: str | None = None,
        errors: list[dict[str, Any]] | None = None,
    ) -> Self:
        return cls(
            detail,
            error_code=ErrorCode.SERVER,
            title=title,
            type_=type_,
            errors=errors,
        )

    @classmethod
    def database(
        cls,
        detail: str | None = None,
        *,
        title: str | None = None,
        type_: str | None = None,
        errors: list[dict[str, Any]] | None = None,
    ) -> Self:
        return cls(
            detail,
            error_code=ErrorCode.DATABASE,
            title=title,
            type_=type_,
            errors=errors,
        )

    @classmethod
    def input(
        cls,
        detail: str | None = None,
        *,
        title: str | None = None,
        type_: str | None = None,
        errors: list[dict[str, Any]] | None = None,
    ) -> Self:
        return cls(
            detail,
            error_code=ErrorCode.INPUT,
            title=title,
            type_=type_,
            errors=errors,
        )

    @classmethod
    def auth(
        cls,
        detail: str | None = None,
        *,
        title: str | None = None,
        type_: str | None = None,
        errors: list[dict[str, Any]] | None = None,
    ) -> Self:
        return cls(
            detail,
            error_code=ErrorCode.AUTH,
            title=title,
            type_=type_,
            errors=errors,
        )

    @classmethod
    def app_check(
        cls,
        detail: str | None = None,
        *,
        title: str | None = None,
        type_: str | None = None,
        errors: list[dict[str, Any]] | None = None,
    ) -> Self:
        return cls(
            detail,
            error_code=ErrorCode.APP_CHECK,
            title=title,
            type_=type_,
            errors=errors,
        )


__all__ = [
    "PROBLEM_TYPES",
    "AppError",
    "ErrorCode",
    "ProblemType",
    "problem_type_uri",
]

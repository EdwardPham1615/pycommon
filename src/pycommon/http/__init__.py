"""HTTP helpers: RFC 9457 Problem Details, API response envelope, pagination, health, client."""

from pycommon.http.client import create_http_client
from pycommon.http.health import HealthCheck, build_health_router
from pycommon.http.pagination import Page, PageMeta, decode_cursor, encode_cursor
from pycommon.http.problem import (
    ProblemDetail,
    app_error_handler,
    build_problem_types_router,
    problem_response,
    register_exception_handlers,
    unhandled_exception_handler,
)
from pycommon.http.response import ApiResponse, Pagination

__all__ = [
    "ApiResponse",
    "HealthCheck",
    "Page",
    "PageMeta",
    "Pagination",
    "ProblemDetail",
    "app_error_handler",
    "build_health_router",
    "build_problem_types_router",
    "create_http_client",
    "decode_cursor",
    "encode_cursor",
    "problem_response",
    "register_exception_handlers",
    "unhandled_exception_handler",
]

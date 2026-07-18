"""HTTP helpers: RFC 9457 Problem Details, pagination, health checks, client factory."""

from pycommon.http.client import create_http_client
from pycommon.http.health import HealthCheck, build_health_router
from pycommon.http.pagination import Page, PageMeta, decode_cursor, encode_cursor
from pycommon.http.problem import (
    ProblemDetail,
    app_error_handler,
    problem_response,
    register_exception_handlers,
    unhandled_exception_handler,
)

__all__ = [
    "HealthCheck",
    "Page",
    "PageMeta",
    "ProblemDetail",
    "app_error_handler",
    "build_health_router",
    "create_http_client",
    "decode_cursor",
    "encode_cursor",
    "problem_response",
    "register_exception_handlers",
    "unhandled_exception_handler",
]

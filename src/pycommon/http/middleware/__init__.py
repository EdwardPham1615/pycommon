"""Common reusable HTTP middleware."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi.middleware.cors import CORSMiddleware

from pycommon.http.middleware.metrics import MetricsMiddleware
from pycommon.http.middleware.request_context import (
    REQUEST_ID_HEADER,
    RequestContextMiddleware,
    client_ip,
)
from pycommon.http.middleware.security_headers import (
    API_CONTENT_SECURITY_POLICY,
    SecurityHeadersMiddleware,
)
from pycommon.http.middleware.timeout import (
    DEFAULT_EXCLUDE_PATHS,
    TimeoutMiddleware,
)

if TYPE_CHECKING:
    from fastapi import FastAPI

    from pycommon.config import BaseAppSettings

__all__ = [
    "API_CONTENT_SECURITY_POLICY",
    "DEFAULT_EXCLUDE_PATHS",
    "REQUEST_ID_HEADER",
    "MetricsMiddleware",
    "RequestContextMiddleware",
    "SecurityHeadersMiddleware",
    "TimeoutMiddleware",
    "apply_standard_middleware",
    "client_ip",
]


def apply_standard_middleware(
    app: FastAPI,
    settings: BaseAppSettings,
    *,
    metrics: bool = True,
) -> None:
    """Attach the standard middleware stack in the correct order.

    Outermost to innermost: CORS, security headers, metrics, request context
    (request-ID + access log + unhandled-exception rendering).
    Starlette treats the *last* added middleware as outermost, hence the
    reversed add order below.

    Request context must sit *inside* the other two: it renders unhandled
    exceptions itself (see :class:`RequestContextMiddleware`), and that response
    only picks up security and CORS headers if those layers wrap it. Metrics sit
    just outside it so those rendered 500s are counted as 500s.

    ``metrics`` records RED metrics through the OTel API; they stay no-ops until
    :func:`~pycommon.telemetry.metrics.setup_metrics` installs a provider, so
    leaving it on costs nothing in a service that exports no metrics.

    Everything that varies between deployments is read from ``settings.http``
    (``HTTP__TIMEOUT_SECONDS``, ``HTTP__CONTENT_SECURITY_POLICY``, ``HTTP__HSTS``,
    ``HTTP__HSTS_MAX_AGE``) the same way CORS already is, so a value has exactly
    one source and an operator can change it without a code change. ``metrics``
    stays an argument because it is structural rather than
    environment-specific — whether this service records HTTP metrics at all,
    not what its ceiling should be.
    """
    # Innermost, so the 504 it produces travels back out through the request
    # context (request ID, access log) and the metrics layer (counted as a 504)
    # exactly like any other response.
    if settings.http.timeout_seconds is not None:
        app.add_middleware(TimeoutMiddleware, seconds=settings.http.timeout_seconds)
    app.add_middleware(RequestContextMiddleware)
    if metrics:
        app.add_middleware(MetricsMiddleware)
    app.add_middleware(
        SecurityHeadersMiddleware,
        content_security_policy=settings.http.content_security_policy,
        hsts=settings.http.hsts,
        hsts_max_age=settings.http.hsts_max_age,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=settings.cors_allow_methods,
        allow_headers=settings.cors_allow_headers,
    )

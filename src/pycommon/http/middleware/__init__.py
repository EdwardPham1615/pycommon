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

if TYPE_CHECKING:
    from fastapi import FastAPI

    from pycommon.config import BaseAppSettings

__all__ = [
    "API_CONTENT_SECURITY_POLICY",
    "REQUEST_ID_HEADER",
    "MetricsMiddleware",
    "RequestContextMiddleware",
    "SecurityHeadersMiddleware",
    "apply_standard_middleware",
    "client_ip",
]


def apply_standard_middleware(
    app: FastAPI,
    settings: BaseAppSettings,
    *,
    metrics: bool = True,
    content_security_policy: str | None = None,
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

    ``content_security_policy`` is off by default; see
    :class:`SecurityHeadersMiddleware` for why there is no safe default, and
    :data:`~pycommon.http.middleware.security_headers.API_CONTENT_SECURITY_POLICY`
    for the value a JSON-only API wants.
    """
    app.add_middleware(RequestContextMiddleware)
    if metrics:
        app.add_middleware(MetricsMiddleware)
    app.add_middleware(SecurityHeadersMiddleware, content_security_policy=content_security_policy)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=settings.cors_allow_methods,
        allow_headers=settings.cors_allow_headers,
    )

"""Common reusable HTTP middleware."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi.middleware.cors import CORSMiddleware

from pycommon.http.middleware.request_context import (
    REQUEST_ID_HEADER,
    RequestContextMiddleware,
)
from pycommon.http.middleware.security_headers import SecurityHeadersMiddleware

if TYPE_CHECKING:
    from fastapi import FastAPI

    from pycommon.config import BaseAppSettings

__all__ = [
    "REQUEST_ID_HEADER",
    "RequestContextMiddleware",
    "SecurityHeadersMiddleware",
    "apply_standard_middleware",
]


def apply_standard_middleware(app: FastAPI, settings: BaseAppSettings) -> None:
    """Attach the standard middleware stack in the correct order.

    Outermost to innermost: CORS (so even error responses get CORS headers),
    request context (request-ID + access log), security headers.
    Starlette treats the *last* added middleware as outermost, hence the
    reversed add order below.
    """
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=settings.cors_allow_methods,
        allow_headers=settings.cors_allow_headers,
    )

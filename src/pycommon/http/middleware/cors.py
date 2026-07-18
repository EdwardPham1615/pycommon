"""Standard CORS middleware factory."""

from __future__ import annotations

from fastapi.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp


def build_cors_middleware(
    app: ASGIApp,
    *,
    allow_origins: list[str],
    allow_credentials: bool = True,
    allow_methods: list[str] | None = None,
    allow_headers: list[str] | None = None,
) -> CORSMiddleware:
    """Wrap app with CORSMiddleware using standardized defaults."""
    return CORSMiddleware(
        app,
        allow_origins=allow_origins,
        allow_credentials=allow_credentials,
        allow_methods=allow_methods or ["*"],
        allow_headers=allow_headers or ["*"],
    )

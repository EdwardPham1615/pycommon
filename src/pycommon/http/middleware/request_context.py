"""Request-ID + OpenTelemetry context binding for structlog."""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from typing import Any

import structlog
from opentelemetry import trace
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

REQUEST_ID_HEADER = "X-Request-ID"


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Generate/propagate request ID, bind OTel + request context to structlog."""

    def __init__(self, app: ASGIApp, header_name: str = REQUEST_ID_HEADER) -> None:
        super().__init__(app)
        self.header_name = header_name

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = request.headers.get(self.header_name) or str(uuid.uuid4())
        structlog.contextvars.clear_contextvars()

        span = trace.get_current_span()
        ctx = span.get_span_context() if span else None
        bind: dict[str, Any] = {
            "request_id": request_id,
            "http": {
                "request": {
                    "method": request.method,
                    "id": request_id,
                }
            },
            "url": {"path": request.url.path},
        }
        if ctx and ctx.is_valid:
            bind["trace"] = {"id": format(ctx.trace_id, "032x")}
            bind["span"] = {"id": format(ctx.span_id, "016x")}

        structlog.contextvars.bind_contextvars(**bind)
        request.state.request_id = request_id

        start = time.perf_counter()
        logger = structlog.get_logger("access")
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - start) * 1000
            logger.exception(
                "request_failed",
                duration_ms=round(duration_ms, 2),
            )
            raise

        duration_ms = (time.perf_counter() - start) * 1000
        response.headers[self.header_name] = request_id
        logger.info(
            "request_completed",
            status_code=response.status_code,
            duration_ms=round(duration_ms, 2),
        )
        return response

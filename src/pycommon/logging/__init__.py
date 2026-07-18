"""ECS-structured logging with OpenTelemetry correlation."""

from __future__ import annotations

import logging
import sys
from typing import Any

import ecs_logging
import structlog
from opentelemetry import trace


def _add_otel_context(
    logger: Any,
    method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """Inject OpenTelemetry trace/span IDs into every log event (ECS tracing fields)."""
    span = trace.get_current_span()
    ctx = span.get_span_context() if span else None
    if ctx and ctx.is_valid:
        event_dict["trace"] = {
            "id": format(ctx.trace_id, "032x"),
        }
        event_dict["span"] = {
            "id": format(ctx.span_id, "016x"),
        }
    return event_dict


def _add_service_info(
    service_name: str,
    environment: str,
) -> Any:
    def processor(
        logger: Any,
        method_name: str,
        event_dict: dict[str, Any],
    ) -> dict[str, Any]:
        event_dict.setdefault(
            "service",
            {"name": service_name, "environment": environment},
        )
        return event_dict

    return processor


def setup_logging(
    *,
    level: str = "INFO",
    service_name: str = "app",
    environment: str = "dev",
    json_logs: bool = True,
) -> None:
    """Configure structlog + stdlib logging for ECS JSON output."""
    log_level = getattr(logging, level.upper(), logging.INFO)

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        _add_otel_context,
        _add_service_info(service_name, environment),
    ]

    if json_logs:
        # ecs_logging.StructlogFormatter must be last — it handles JSON + ECS enrichment
        renderer: Any = ecs_logging.StructlogFormatter()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(log_level)

    # Quiet noisy libs
    for name in ("uvicorn.access", "httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    return logger

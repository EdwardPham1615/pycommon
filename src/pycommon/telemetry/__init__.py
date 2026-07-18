"""OpenTelemetry bootstrap for FastAPI services."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBasedTraceIdRatio

from pycommon.logging import get_logger
from pycommon.telemetry.profiler import enable_profiler

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = get_logger(__name__)

_provider: TracerProvider | None = None

__all__ = [
    "enable_profiler",
    "instrument_sqlalchemy",
    "setup_telemetry",
    "shutdown_telemetry",
]


def setup_telemetry(
    app: FastAPI,
    *,
    service_name: str,
    otlp_endpoint: str = "http://localhost:4317",
    insecure: bool = True,
    sampler_arg: float = 1.0,
    enabled: bool = True,
    environment: str = "dev",
) -> TracerProvider | None:
    """Initialize the OTel SDK and instrument FastAPI + common client libraries.

    Returns the active ``TracerProvider`` (or ``None`` when disabled). The
    global provider is created once per process; subsequent calls reuse it and
    only instrument the given app. Call :func:`shutdown_telemetry` on app
    shutdown to flush buffered spans.
    """
    global _provider
    if not enabled:
        return None

    if _provider is None:
        resource = Resource.create(
            {
                "service.name": service_name,
                "deployment.environment": environment,
            }
        )
        _provider = TracerProvider(
            resource=resource,
            sampler=ParentBasedTraceIdRatio(sampler_arg),
        )
        exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=insecure)
        _provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(_provider)
    else:
        logger.warning(
            "telemetry_already_initialized",
            detail="TracerProvider already set; reusing it and ignoring new exporter settings",
        )

    _instrument_libraries(app)
    return _provider


def shutdown_telemetry() -> None:
    """Flush and shut down the tracer provider (call from app shutdown/lifespan)."""
    global _provider
    if _provider is None:
        return
    try:
        _provider.shutdown()
    except Exception:
        logger.exception("telemetry_shutdown_failed")
    finally:
        _provider = None


def _instrument_libraries(app: FastAPI) -> None:
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        if not getattr(app.state, "_otel_fastapi_instrumented", False):
            FastAPIInstrumentor.instrument_app(app, excluded_urls="health,ready,live")
            app.state._otel_fastapi_instrumented = True
    except ImportError:
        logger.warning("otel_instrumentor_unavailable", instrumentor="fastapi")
    except Exception:
        logger.exception("otel_instrumentation_failed", instrumentor="fastapi")

    for mod_path, attr in (
        ("opentelemetry.instrumentation.httpx", "HTTPXClientInstrumentor"),
        ("opentelemetry.instrumentation.redis", "RedisInstrumentor"),
        ("opentelemetry.instrumentation.pymongo", "PymongoInstrumentor"),
        ("opentelemetry.instrumentation.celery", "CeleryInstrumentor"),
    ):
        try:
            module = __import__(mod_path, fromlist=[attr])
            instrumentor = getattr(module, attr)()
            if not getattr(instrumentor, "is_instrumented_by_opentelemetry", False):
                instrumentor.instrument()
        except ImportError:
            # Optional instrumentation — the target library isn't installed.
            pass
        except Exception:
            logger.exception("otel_instrumentation_failed", instrumentor=attr)


def instrument_sqlalchemy(engine: Any) -> None:
    try:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

        SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)
    except ImportError:
        logger.warning("otel_instrumentor_unavailable", instrumentor="sqlalchemy")
    except Exception:
        logger.exception("otel_instrumentation_failed", instrumentor="sqlalchemy")

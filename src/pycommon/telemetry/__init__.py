"""OpenTelemetry bootstrap for FastAPI services."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBasedTraceIdRatio

if TYPE_CHECKING:
    from fastapi import FastAPI

_PROVIDER_SET = False


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
    """Initialize OTel SDK and instrument FastAPI. Returns TracerProvider or None if disabled."""
    global _PROVIDER_SET
    if not enabled:
        return None

    provider: TracerProvider | None = None
    if not _PROVIDER_SET:
        resource = Resource.create(
            {
                "service.name": service_name,
                "deployment.environment": environment,
            }
        )
        provider = TracerProvider(
            resource=resource,
            sampler=ParentBasedTraceIdRatio(sampler_arg),
        )
        exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=insecure)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        _PROVIDER_SET = True

    _instrument_libraries(app)
    return provider


def _instrument_libraries(app: FastAPI) -> None:
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        if not getattr(app.state, "_otel_fastapi_instrumented", False):
            FastAPIInstrumentor.instrument_app(app, excluded_urls="health,ready,live")
            app.state._otel_fastapi_instrumented = True
    except Exception:  # noqa: S110
        pass

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
        except Exception:  # noqa: S110
            pass


def instrument_sqlalchemy(engine: Any) -> None:
    try:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

        SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)
    except Exception:  # noqa: S110
        pass

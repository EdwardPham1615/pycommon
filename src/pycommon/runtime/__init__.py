"""Reusable server runtime: FastAPI shell, lifespan composition, gRPC, uvicorn."""

from pycommon.runtime.app import create_base_app
from pycommon.runtime.grpc import GrpcServer, ServicerRegistrar, default_otel_interceptors
from pycommon.runtime.grpc_client import GrpcChannelPool, default_otel_client_interceptors
from pycommon.runtime.grpc_interceptors import (
    RequestIdClientInterceptor,
    RequestIdServerInterceptor,
    RequestIdStreamStreamClientInterceptor,
    RequestIdStreamUnaryClientInterceptor,
    RequestIdUnaryStreamClientInterceptor,
    request_id_client_interceptors,
    request_id_server_interceptors,
)
from pycommon.runtime.grpc_metrics import MetricsServerInterceptor, metrics_server_interceptors
from pycommon.runtime.lifespan import LifespanResource, build_lifespan
from pycommon.runtime.uvicorn import DrainingServer, run_from_settings, run_uvicorn

__all__ = [
    "DrainingServer",
    "GrpcChannelPool",
    "GrpcServer",
    "LifespanResource",
    "MetricsServerInterceptor",
    "RequestIdClientInterceptor",
    "RequestIdServerInterceptor",
    "RequestIdStreamStreamClientInterceptor",
    "RequestIdStreamUnaryClientInterceptor",
    "RequestIdUnaryStreamClientInterceptor",
    "ServicerRegistrar",
    "build_lifespan",
    "create_base_app",
    "default_otel_client_interceptors",
    "default_otel_interceptors",
    "metrics_server_interceptors",
    "request_id_client_interceptors",
    "request_id_server_interceptors",
    "run_from_settings",
    "run_uvicorn",
]

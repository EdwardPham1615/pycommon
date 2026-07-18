"""Smoke tests: every public submodule must be importable when extras are installed."""

from __future__ import annotations


def test_import_package() -> None:
    import pycommon

    assert pycommon.__version__ == "0.1.0"


def test_import_config() -> None:
    from pycommon.config import BaseAppSettings, Environment

    assert Environment.DEV == "dev"
    assert BaseAppSettings is not None


def test_import_logging() -> None:
    from pycommon.logging import get_logger, setup_logging

    assert callable(setup_logging)
    assert callable(get_logger)


def test_import_telemetry() -> None:
    from pycommon.telemetry import (
        enable_profiler,
        instrument_sqlalchemy,
        setup_telemetry,
        shutdown_telemetry,
    )

    assert callable(setup_telemetry)
    assert callable(shutdown_telemetry)
    assert callable(instrument_sqlalchemy)
    assert callable(enable_profiler)


def test_import_security() -> None:
    from pycommon.security import (
        ClientCredentialsTokenProvider,
        KeycloakTokenValidator,
        TokenClaims,
        create_auth_deps,
    )

    assert TokenClaims is not None
    assert KeycloakTokenValidator is not None
    assert ClientCredentialsTokenProvider is not None
    assert callable(create_auth_deps)


def test_import_storage() -> None:
    from pycommon.storage import ObjectStorageClient

    assert ObjectStorageClient is not None


def test_import_errors() -> None:
    from pycommon.errors import AppError, ConflictError, NotFoundError

    assert issubclass(NotFoundError, AppError)
    assert issubclass(ConflictError, AppError)


def test_import_http() -> None:
    from pycommon.http import (
        HealthCheck,
        Page,
        ProblemDetail,
        build_health_router,
        create_http_client,
        problem_response,
        register_exception_handlers,
    )

    assert ProblemDetail is not None
    assert Page is not None
    assert HealthCheck is not None
    assert callable(problem_response)
    assert callable(build_health_router)
    assert callable(create_http_client)
    assert callable(register_exception_handlers)


def test_import_http_middleware() -> None:
    from pycommon.http.middleware import (
        RequestContextMiddleware,
        SecurityHeadersMiddleware,
        apply_standard_middleware,
    )
    from pycommon.http.middleware.rate_limit import build_rate_limit_dep

    assert RequestContextMiddleware is not None
    assert SecurityHeadersMiddleware is not None
    assert callable(apply_standard_middleware)
    assert callable(build_rate_limit_dep)


def test_import_cache() -> None:
    from pycommon.cache import (
        InMemoryRateLimiter,
        RedisRateLimiter,
        create_redis,
        redis_lock,
    )

    assert callable(create_redis)
    assert callable(redis_lock)
    assert InMemoryRateLimiter is not None
    assert RedisRateLimiter is not None


def test_import_runtime() -> None:
    from pycommon.runtime import (
        GrpcChannelPool,
        GrpcServer,
        LifespanResource,
        RequestIdClientInterceptor,
        RequestIdServerInterceptor,
        build_lifespan,
        create_base_app,
        run_uvicorn,
    )

    assert callable(create_base_app)
    assert callable(build_lifespan)
    assert LifespanResource is not None
    assert GrpcServer is not None
    assert GrpcChannelPool is not None
    assert RequestIdServerInterceptor is not None
    assert RequestIdClientInterceptor is not None
    assert callable(run_uvicorn)


def test_import_persistence() -> None:
    from pycommon.persistence import (
        Repository,
        SqlAlchemyRepository,
        SqlAlchemyUnitOfWork,
        UnitOfWork,
        create_engine_and_sessionmaker,
    )

    assert Repository is not None
    assert SqlAlchemyRepository is not None
    assert UnitOfWork is not None
    assert SqlAlchemyUnitOfWork is not None
    assert callable(create_engine_and_sessionmaker)


def test_import_utils() -> None:
    from pycommon.utils import (
        AsyncCircuitBreaker,
        FixedClock,
        new_nanoid,
        new_uuid7,
        retry_async,
        standard_retry,
        utcnow,
    )

    assert callable(retry_async)
    assert callable(standard_retry)
    assert callable(new_nanoid)
    assert callable(new_uuid7)
    assert AsyncCircuitBreaker is not None
    assert FixedClock is not None
    assert utcnow().tzinfo is not None


def test_import_config_profiler_settings() -> None:
    from pycommon.config import ProfilerSettings

    assert ProfilerSettings().enabled is False


def test_import_testing() -> None:
    from pycommon.testing.fakes import FakeUnitOfWork, InMemoryRepository
    from pycommon.testing.tokens import generate_rsa_keypair, issue_test_token

    assert FakeUnitOfWork is not None
    assert InMemoryRepository is not None
    assert callable(generate_rsa_keypair)
    assert callable(issue_test_token)

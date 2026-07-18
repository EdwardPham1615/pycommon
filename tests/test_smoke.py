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
    from pycommon.telemetry import instrument_sqlalchemy, setup_telemetry

    assert callable(setup_telemetry)
    assert callable(instrument_sqlalchemy)


def test_import_security() -> None:
    from pycommon.security import KeycloakTokenValidator, TokenClaims, create_auth_deps

    assert TokenClaims is not None
    assert KeycloakTokenValidator is not None
    assert callable(create_auth_deps)


def test_import_storage() -> None:
    from pycommon.storage import ObjectStorageClient

    assert ObjectStorageClient is not None


def test_import_http() -> None:
    from pycommon.http import Page, ProblemDetail, problem_response

    assert ProblemDetail is not None
    assert Page is not None
    assert callable(problem_response)


def test_import_http_middleware() -> None:
    from pycommon.http.middleware import cors, request_context, security_headers

    assert cors is not None
    assert request_context is not None
    assert security_headers is not None


def test_import_runtime() -> None:
    from pycommon.runtime import (
        GrpcServer,
        LifespanResource,
        build_lifespan,
        create_base_app,
        run_uvicorn,
    )

    assert callable(create_base_app)
    assert callable(build_lifespan)
    assert LifespanResource is not None
    assert GrpcServer is not None
    assert callable(run_uvicorn)


def test_import_persistence() -> None:
    from pycommon.persistence import (
        Repository,
        SqlAlchemyRepository,
        SqlAlchemyUnitOfWork,
        UnitOfWork,
    )

    assert Repository is not None
    assert SqlAlchemyRepository is not None
    assert UnitOfWork is not None
    assert SqlAlchemyUnitOfWork is not None

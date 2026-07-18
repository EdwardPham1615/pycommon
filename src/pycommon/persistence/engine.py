"""Async engine / sessionmaker factory wired from DatabaseSettings."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from pycommon.config import DatabaseSettings
from pycommon.logging import get_logger
from pycommon.runtime.lifespan import LifespanResource

logger = get_logger(__name__)


def create_engine_and_sessionmaker(
    settings: DatabaseSettings,
    *,
    instrument: bool = True,
) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    """Create an async engine + sessionmaker with standard pool settings.

    When ``instrument=True`` and the OTel SQLAlchemy instrumentation is
    installed, the engine is instrumented automatically.
    """
    engine = create_async_engine(
        settings.async_dsn,
        pool_size=settings.pool_size,
        max_overflow=settings.max_overflow,
        pool_pre_ping=settings.pool_pre_ping,
        echo=settings.echo,
    )
    if instrument:
        try:
            from pycommon.telemetry import instrument_sqlalchemy

            instrument_sqlalchemy(engine)
        except ImportError:
            logger.warning("sqlalchemy_instrumentation_unavailable")

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    return engine, session_factory


def database_lifespan_resource(
    engine: AsyncEngine,
    *,
    name: str = "database",
) -> LifespanResource:
    """LifespanResource that verifies connectivity on startup and disposes the pool on shutdown."""

    async def startup() -> None:
        async with engine.connect():
            pass

    async def shutdown() -> None:
        await engine.dispose()

    return LifespanResource(name=name, startup=startup, shutdown=shutdown)

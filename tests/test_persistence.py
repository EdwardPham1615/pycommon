"""Repository + UnitOfWork behavior against an in-memory SQLite database."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from sqlalchemy import String
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from pycommon.persistence import SqlAlchemyRepository, SqlAlchemyUnitOfWork


class Base(DeclarativeBase):
    pass


class Item(Base):
    __tablename__ = "items"

    item_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50))


class ItemRepository(SqlAlchemyRepository[Item, int]):
    model = Item


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session


async def test_crud_with_non_uuid_custom_named_pk(session: AsyncSession) -> None:
    """PK is `item_id: int`, not `id: UUID` — repository must not care."""
    repo = ItemRepository(session)

    created = await repo.create(Item(name="widget"))
    assert created.item_id is not None

    fetched = await repo.get(created.item_id)
    assert fetched is not None and fetched.name == "widget"

    fetched.name = "gadget"
    updated = await repo.update(fetched)
    assert updated.name == "gadget"

    assert await repo.delete(created.item_id) is True
    assert await repo.get(created.item_id) is None


async def test_delete_missing_returns_false(session: AsyncSession) -> None:
    repo = ItemRepository(session)
    assert await repo.delete(9999) is False


async def test_get_list_pagination(session: AsyncSession) -> None:
    repo = ItemRepository(session)
    for i in range(5):
        await repo.create(Item(name=f"item-{i}"))

    page = await repo.get_list(limit=2, offset=2, order_by=Item.item_id)
    assert [i.name for i in page] == ["item-2", "item-3"]


async def test_uow_commits_on_success(engine: AsyncEngine) -> None:
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with SqlAlchemyUnitOfWork(factory) as uow:
        assert uow.session is not None
        uow.session.add(Item(name="committed"))

    async with factory() as check:
        repo = ItemRepository(check)
        items = await repo.get_list()
        assert [i.name for i in items] == ["committed"]


async def test_uow_rolls_back_on_error(engine: AsyncEngine) -> None:
    factory = async_sessionmaker(engine, expire_on_commit=False)

    with pytest.raises(RuntimeError, match="boom"):
        async with SqlAlchemyUnitOfWork(factory) as uow:
            assert uow.session is not None
            uow.session.add(Item(name="doomed"))
            raise RuntimeError("boom")

    async with factory() as check:
        repo = ItemRepository(check)
        assert await repo.get_list() == []


async def test_query_logger_emits_structured_log() -> None:
    from structlog.testing import capture_logs

    from pycommon.persistence.query_logging import install_query_logger

    engine = create_async_engine("sqlite+aiosqlite://")
    install_query_logger(engine, slow_query_threshold_ms=0.0)
    with capture_logs() as logs:
        async with engine.connect() as conn:
            await conn.exec_driver_sql("SELECT 1")
    await engine.dispose()

    query_logs = [entry for entry in logs if entry.get("event") == "db_query"]
    assert query_logs
    entry = query_logs[0]
    assert "SELECT 1" in entry["db"]["statement"]
    assert isinstance(entry["duration_ms"], float)


async def test_query_logger_threshold_skips_fast_queries() -> None:
    from structlog.testing import capture_logs

    from pycommon.persistence.query_logging import install_query_logger

    engine = create_async_engine("sqlite+aiosqlite://")
    install_query_logger(engine, slow_query_threshold_ms=60_000.0)
    with capture_logs() as logs:
        async with engine.connect() as conn:
            await conn.exec_driver_sql("SELECT 1")
    await engine.dispose()

    assert [entry for entry in logs if entry.get("event") in {"db_query", "slow_query"}] == []


async def test_migration_lifespan_skips_when_disabled() -> None:
    from structlog.testing import capture_logs

    from pycommon.config import DatabaseSettings
    from pycommon.persistence import migration_lifespan_resource

    settings = DatabaseSettings(auto_migrate=False)
    resource = migration_lifespan_resource(settings)
    with capture_logs() as logs:
        await resource.startup()
    assert any(entry.get("event") == "migrations_skipped" for entry in logs)

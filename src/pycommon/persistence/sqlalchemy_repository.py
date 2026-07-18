"""Generic SQLAlchemy async repository base."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, cast

from sqlalchemy import CursorResult, Select, delete, inspect, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase

from pycommon.persistence.repository import Repository


class SqlAlchemyRepository[ModelT: DeclarativeBase, IdT](Repository[ModelT, IdT]):
    """CRUD helpers for a single SQLAlchemy mapped class.

    The primary-key column is derived from the mapper (single-column PKs of any
    type/name). Subclasses may override ``_base_select`` (e.g. to add
    ``selectinload``), ``create`` / ``update`` (e.g. to refresh specific
    relationships), or ``get_list`` (filters / ordering).
    """

    model: type[ModelT]
    _default_order_by: Any | None = None

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @property
    def _pk_column(self) -> Any:
        pk_columns = inspect(self.model).primary_key
        if len(pk_columns) != 1:
            raise TypeError(
                f"{type(self).__name__} requires a single-column primary key; "
                f"{self.model.__name__} has {len(pk_columns)}"
            )
        return pk_columns[0]

    def _base_select(self) -> Select[tuple[ModelT]]:
        return select(self.model)

    async def create(self, entity: ModelT) -> ModelT:
        self.session.add(entity)
        await self.session.flush()
        await self.session.refresh(entity)
        return entity

    async def get(self, entity_id: IdT) -> ModelT | None:
        result = await self.session.execute(self._base_select().where(self._pk_column == entity_id))
        return result.scalar_one_or_none()

    async def get_list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        order_by: Any | None = None,
    ) -> Sequence[ModelT]:
        stmt = self._base_select()
        ordering = order_by if order_by is not None else self._default_order_by
        if ordering is not None:
            if isinstance(ordering, (list, tuple)):
                stmt = stmt.order_by(*ordering)
            else:
                stmt = stmt.order_by(ordering)
        stmt = stmt.limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update(self, entity: ModelT) -> ModelT:
        await self.session.flush()
        await self.session.refresh(entity)
        return entity

    async def delete(self, entity_id: IdT) -> bool:
        result = await self.session.execute(delete(self.model).where(self._pk_column == entity_id))
        await self.session.flush()
        # execute() on a DELETE always yields a CursorResult with rowcount.
        return bool(cast("CursorResult[Any]", result).rowcount)

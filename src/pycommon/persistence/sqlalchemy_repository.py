"""Generic SQLAlchemy async repository base."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase

from pycommon.persistence.repository import Repository


class SqlAlchemyRepository[ModelT: DeclarativeBase](Repository[ModelT, uuid.UUID]):
    """CRUD helpers for a single SQLAlchemy mapped class.

    Subclasses may override ``_base_select`` (e.g. to add ``selectinload``),
    ``create`` / ``update`` (e.g. to refresh specific relationships), or
    ``get_list`` (filters / ordering).
    """

    model: type[ModelT]
    _default_order_by: Any | None = None

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _base_select(self) -> Select[tuple[ModelT]]:
        return select(self.model)

    async def create(self, entity: ModelT) -> ModelT:
        self.session.add(entity)
        await self.session.flush()
        await self.session.refresh(entity)
        return entity

    async def get(self, entity_id: uuid.UUID) -> ModelT | None:
        result = await self.session.execute(
            self._base_select().where(self.model.id == entity_id)  # type: ignore[attr-defined]
        )
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

    async def delete(self, entity_id: uuid.UUID) -> bool:
        entity = await self.get(entity_id)
        if entity is None:
            return False
        await self.session.delete(entity)
        await self.session.flush()
        return True

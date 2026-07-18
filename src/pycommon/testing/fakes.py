"""In-memory fakes for persistence abstractions (for service test suites)."""

from __future__ import annotations

from collections.abc import Sequence
from types import TracebackType
from typing import Self

from pycommon.persistence.repository import Repository
from pycommon.persistence.unit_of_work import UnitOfWork


class InMemoryRepository[EntityT, IdT](Repository[EntityT, IdT]):
    """Dict-backed repository. Entities must expose the ``id_attr`` attribute."""

    def __init__(self, *, id_attr: str = "id") -> None:
        self._id_attr = id_attr
        self._items: dict[IdT, EntityT] = {}

    def _id_of(self, entity: EntityT) -> IdT:
        entity_id: IdT = getattr(entity, self._id_attr)
        return entity_id

    async def create(self, entity: EntityT) -> EntityT:
        self._items[self._id_of(entity)] = entity
        return entity

    async def get(self, entity_id: IdT) -> EntityT | None:
        return self._items.get(entity_id)

    async def get_list(self, *, limit: int = 50, offset: int = 0) -> Sequence[EntityT]:
        return list(self._items.values())[offset : offset + limit]

    async def update(self, entity: EntityT) -> EntityT:
        self._items[self._id_of(entity)] = entity
        return entity

    async def delete(self, entity_id: IdT) -> bool:
        return self._items.pop(entity_id, None) is not None


class FakeUnitOfWork(UnitOfWork):
    """Records commit/rollback calls so tests can assert transaction behavior."""

    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False
        self.entered = False
        self.exited = False

    async def __aenter__(self) -> Self:
        self.entered = True
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.exited = True
        if exc_type is not None:
            await self.rollback()
        else:
            await self.commit()

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


__all__: list[str] = ["FakeUnitOfWork", "InMemoryRepository"]

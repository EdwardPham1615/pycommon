"""Generic repository interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence


class Repository[EntityT, IdT](ABC):
    """Single-engine persistence contract.

    Implementations must keep each method single-purpose. Domain-specific
    queries (e.g. ``get_by_email``) live on concrete repositories, not here.
    """

    @abstractmethod
    async def create(self, entity: EntityT) -> EntityT:
        """Persist a new entity and return it (with generated fields populated)."""

    @abstractmethod
    async def get(self, entity_id: IdT) -> EntityT | None:
        """Fetch one entity by primary key, or ``None`` if missing."""

    @abstractmethod
    async def get_list(self, *, limit: int = 50, offset: int = 0) -> Sequence[EntityT]:
        """Return a page of entities."""

    @abstractmethod
    async def update(self, entity: EntityT) -> EntityT:
        """Persist mutations already applied to ``entity`` and return the refreshed row."""

    @abstractmethod
    async def delete(self, entity_id: IdT) -> bool:
        """Delete by primary key. Returns ``True`` if a row was deleted, else ``False``."""

"""Persistence abstractions: engine factory, repository interface, and unit of work."""

from pycommon.persistence.engine import (
    create_engine_and_sessionmaker,
    database_lifespan_resource,
)
from pycommon.persistence.repository import Repository
from pycommon.persistence.sqlalchemy_repository import SqlAlchemyRepository
from pycommon.persistence.sqlalchemy_uow import SqlAlchemyUnitOfWork
from pycommon.persistence.unit_of_work import UnitOfWork

__all__ = [
    "Repository",
    "SqlAlchemyRepository",
    "SqlAlchemyUnitOfWork",
    "UnitOfWork",
    "create_engine_and_sessionmaker",
    "database_lifespan_resource",
]

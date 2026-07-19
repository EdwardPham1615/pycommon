"""Persistence abstractions: engine factory, repository interface, and unit of work."""

from pycommon.persistence.base import NAMING_CONVENTION, Base, metadata
from pycommon.persistence.engine import (
    create_engine_and_sessionmaker,
    database_lifespan_resource,
)
from pycommon.persistence.migrations import (
    build_alembic_config,
    current_revision,
    downgrade,
    migration_lifespan_resource,
    upgrade_to_head,
)
from pycommon.persistence.query_logging import install_query_logger
from pycommon.persistence.repository import Repository
from pycommon.persistence.sqlalchemy_repository import SqlAlchemyRepository
from pycommon.persistence.sqlalchemy_uow import SqlAlchemyUnitOfWork
from pycommon.persistence.unit_of_work import UnitOfWork

__all__ = [
    "NAMING_CONVENTION",
    "Base",
    "Repository",
    "SqlAlchemyRepository",
    "SqlAlchemyUnitOfWork",
    "UnitOfWork",
    "build_alembic_config",
    "create_engine_and_sessionmaker",
    "current_revision",
    "database_lifespan_resource",
    "downgrade",
    "install_query_logger",
    "metadata",
    "migration_lifespan_resource",
    "upgrade_to_head",
]

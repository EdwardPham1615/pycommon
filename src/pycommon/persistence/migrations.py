"""Thin Alembic helpers: config builder, upgrade/downgrade, opt-in lifespan."""

from __future__ import annotations

from typing import Any

from pycommon.config import DatabaseSettings
from pycommon.logging import get_logger
from pycommon.runtime.lifespan import LifespanResource

logger = get_logger(__name__)


def _require_alembic() -> Any:
    try:
        from alembic.config import Config
    except ImportError as exc:
        raise ImportError(
            'Alembic is required for migrations. Install with: pip install "pycommon[migrations]"'
        ) from exc
    return Config


def build_alembic_config(
    settings: DatabaseSettings,
    *,
    script_location: str | None = None,
    version_table: str = "alembic_version",
    ini_section: str = "alembic",
) -> Any:
    """Build an in-memory Alembic ``Config`` from :class:`DatabaseSettings`.

    Uses the sync DSN (``postgresql+psycopg://…``) because Alembic migrations
    run synchronously by default.
    """
    config_cls = _require_alembic()
    location = script_location or settings.migrations_script_location
    config = config_cls()
    config.set_main_option("script_location", location)
    config.set_main_option("sqlalchemy.url", settings.sync_dsn)
    config.set_main_option("version_table", version_table)
    config.config_ini_section = ini_section
    return config


def upgrade_to_head(
    settings: DatabaseSettings,
    *,
    script_location: str | None = None,
) -> None:
    """Run ``alembic upgrade head`` against ``settings.sync_dsn``."""
    from alembic import command

    config = build_alembic_config(settings, script_location=script_location)
    logger.info(
        "alembic_upgrade_head",
        script_location=script_location or settings.migrations_script_location,
    )
    command.upgrade(config, "head")


def downgrade(
    settings: DatabaseSettings,
    *,
    script_location: str | None = None,
    revision: str = "-1",
) -> None:
    """Run ``alembic downgrade <revision>`` (default: one revision)."""
    from alembic import command

    config = build_alembic_config(settings, script_location=script_location)
    logger.info(
        "alembic_downgrade",
        revision=revision,
        script_location=script_location or settings.migrations_script_location,
    )
    command.downgrade(config, revision)


def current_revision(
    settings: DatabaseSettings,
    *,
    script_location: str | None = None,
) -> None:
    """Print the current Alembic revision (via ``alembic current``)."""
    from alembic import command

    config = build_alembic_config(settings, script_location=script_location)
    command.current(config)


def migration_lifespan_resource(
    settings: DatabaseSettings,
    *,
    script_location: str | None = None,
    name: str = "migrations",
) -> LifespanResource:
    """Opt-in Alembic upgrade on startup when ``settings.auto_migrate`` is True.

    Keep ``auto_migrate=False`` in production and run migrations from a deploy
    job instead (avoids multi-instance race conditions).
    """
    location = script_location or settings.migrations_script_location

    async def startup() -> None:
        if not settings.auto_migrate:
            logger.info("migrations_skipped", reason="auto_migrate_disabled")
            return
        upgrade_to_head(settings, script_location=location)

    return LifespanResource(name=name, startup=startup)

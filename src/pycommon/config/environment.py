"""Environment resolution helpers."""

from __future__ import annotations

import os
from enum import StrEnum
from functools import lru_cache
from pathlib import Path


class Environment(StrEnum):
    DEV = "dev"
    STAGING = "staging"
    PRODUCTION = "production"


def resolve_env_files(environment: str | None = None) -> list[str]:
    """Return ordered env files to load (``.env`` then ``.env.{environment}``).

    When passed to pydantic-settings as ``_env_file``, later files take priority,
    so environment-specific values override the base ``.env``.
    """
    env = environment or os.getenv("ENVIRONMENT") or Environment.DEV
    files = [".env", f".env.{env}"]
    return [f for f in files if Path(f).exists()]


@lru_cache
def get_environment() -> Environment:
    """Read ``ENVIRONMENT`` and fail loudly on invalid values.

    Silently falling back to DEV on a typo (e.g. ``prod``) would enable docs and
    relax security in production, so an invalid value raises instead.
    """
    raw = os.getenv("ENVIRONMENT", Environment.DEV)
    try:
        return Environment(raw)
    except ValueError as exc:
        valid = ", ".join(e.value for e in Environment)
        raise ValueError(f"Invalid ENVIRONMENT={raw!r}; expected one of: {valid}") from exc

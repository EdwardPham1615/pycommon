"""Reusable platform library for FastAPI services."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("pycommon")
except PackageNotFoundError:  # pragma: no cover - only when running from a source tree
    # Not installed (e.g. imported straight off a checkout). A hardcoded
    # fallback here would be the second copy of the version this indirection
    # exists to remove, so say so instead of guessing wrong.
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]

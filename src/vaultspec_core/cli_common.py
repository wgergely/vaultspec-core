"""Provide shared utility helpers for CLI entrypoints.

This module supplies small runtime helpers that are reused across console
surfaces, including version discovery and safe async execution. It supports the
CLI entry boundary without defining commands itself.

Usage:
    Use `get_version(...)` to resolve package version text and `run_async(...)`
    to execute async workflows safely from synchronous CLI entrypoints.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import sys
import warnings
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    from collections.abc import Coroutine

logger = logging.getLogger(__name__)

T = TypeVar("T")


def get_version(root_dir: Path | None = None) -> str:
    """Read the package version, preferring importlib.metadata for pip-installed usage.

    Tries ``importlib.metadata.version("vaultspec-core")`` first (correct when
    pip-installed), then falls back to pyproject.toml line-scanning for
    development mode (running from source without install).

    Args:
        root_dir: Directory containing ``pyproject.toml`` for the fallback path.
            Falls back to ``Path.cwd()`` if ``None``.

    Returns:
        The version string, or ``"unknown"`` if it cannot be determined.
    """
    try:
        from importlib.metadata import version

        return version("vaultspec-core")
    except Exception:
        pass
    search_root = root_dir if root_dir is not None else Path.cwd()
    toml_path = search_root / "pyproject.toml"
    if toml_path.exists():
        for line in toml_path.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("version"):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return "unknown"


def run_async[T](coro: Coroutine[Any, Any, T], *, debug: bool = False) -> T:
    """Run a coroutine on a new event loop with Windows-safe teardown.

    Applies ``WindowsProactorEventLoopPolicy`` on Windows and suppresses
    ``ResourceWarning`` during the run. A short grace period is added on
    Windows before loop close to flush pending pipe callbacks.

    On unhandled exceptions (other than ``KeyboardInterrupt`` / ``SystemExit``),
    logs the error and calls ``sys.exit(1)``.

    Args:
        coro: The coroutine to run.
        debug: If ``True``, print a full traceback on unhandled exceptions.

    Returns:
        The return value of the coroutine.
    """
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ResourceWarning)
            return loop.run_until_complete(coro)
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception as exc:
        logger.error("Error: %s", exc, exc_info=debug)
        raise SystemExit(1) from exc
    finally:
        if sys.platform == "win32":
            with contextlib.suppress(Exception):
                loop.run_until_complete(asyncio.sleep(0.250))
        loop.close()

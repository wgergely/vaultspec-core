"""Configure process-wide logging for vault/spec-core entry surfaces.

This module centralizes RichHandler-based stderr logging setup and reset
behavior for CLI and MCP runtime entrypoints. It exists to keep diagnostic
output consistent without mixing it into normal user-facing stdout surfaces.

Usage:
    Call `configure_logging(...)` at process bootstrap to install the desired
    logging level, handler behavior, and output stream policy.
"""

from __future__ import annotations

import logging
import os

from rich.console import Console
from rich.logging import RichHandler

__all__ = ["configure_logging", "get_console", "reset_logging"]

# Shared Rich console instance (stderr, no syntax highlighting)
_console: Console | None = None

# Global flag to prevent multiple configurations
_configured: bool = False


def get_console() -> Console:
    """Return the shared Rich console singleton (stderr, no highlighting).

    Creates the instance on first call.

    Returns:
        The shared :class:`rich.console.Console` writing to ``stderr``.
    """
    global _console
    if _console is None:
        _console = Console(stderr=True, highlight=False)
    return _console


def reset_logging() -> None:
    """Reset the logging configuration flag.

    Allows :func:`configure_logging` to be called again.  Primarily used for
    testing logging dispatch.
    """
    global _configured
    _configured = False


def configure_logging(
    level: str | int | None = None,
    debug: bool = False,
    quiet: bool = False,
) -> None:
    """Configure the root logger with a RichHandler.

    Sets the log level based on provided arguments or the
    ``VAULTSPEC_LOG_LEVEL`` environment variable.  Prevents re-configuration
    unless :func:`reset_logging` is called.

    Args:
        level: Explicit log level (e.g. ``logging.INFO`` or ``"DEBUG"``).
        debug: When ``True``, forces level to ``DEBUG`` and enables rich
            tracebacks with local variables.
        quiet: When ``True``, forces level to ``WARNING``.
    """
    global _configured
    if _configured:
        return

    # 1. Resolve level
    if debug:
        resolved_level = logging.DEBUG
    elif quiet:
        resolved_level = logging.WARNING
    elif level is not None:
        if isinstance(level, str):
            resolved_level = getattr(logging, level.upper(), logging.INFO)
        else:
            resolved_level = level
    else:
        # Fallback to environment or default
        env_level = os.environ.get("VAULTSPEC_LOG_LEVEL", "INFO").upper()
        resolved_level = getattr(logging, env_level, logging.INFO)

    # 2. Configure root logger
    root = logging.getLogger()
    root.setLevel(resolved_level)

    # Clear any existing handlers to avoid duplicates
    for handler in root.handlers[:]:
        root.removeHandler(handler)

    # 3. Add RichHandler
    console = get_console()
    handler = RichHandler(
        console=console,
        show_time=debug,
        show_path=debug,
        rich_tracebacks=True,
        tracebacks_show_locals=debug,
        markup=False,
    )
    handler.setLevel(resolved_level)
    root.addHandler(handler)

    _configured = True

"""Central, idempotent logging configuration for vaultspec."""

import logging
import os
import sys

from rich.console import Console

__all__ = ["configure_logging", "get_console", "reset_logging"]

# Module-level flag to ensure idempotency
_logging_configured = False

# Shared Rich console instance (stderr, no syntax highlighting)
_console: Console | None = None

_DEBUG_FORMAT = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"


def get_console() -> Console:
    """Return the shared Rich console singleton (stderr, no highlighting).

    Creates the instance on first call. Safe to call before or after
    ``configure_logging()``.

    Returns:
        The shared :class:`rich.console.Console` writing to ``stderr``.
    """
    global _console
    if _console is None:
        _console = Console(stderr=True, highlight=False)
    return _console


def configure_logging(
    level: str | None = None,
    debug: bool = False,
    quiet: bool = False,
    log_format: str | None = None,
) -> None:
    """Configure logging for vaultspec.

    This function is idempotent and safe to call multiple times.

    Args:
        level: Optional log level override (DEBUG, INFO, WARNING, ERROR, CRITICAL).
               If None, reads from VAULTSPEC_LOG_LEVEL env var, defaults to INFO.
        debug: If True, forces log level to DEBUG. Overrides level param.
        quiet: If True, forces log level to WARNING. Overridden by debug.
        log_format: Optional format string for the log handler.
                    When provided, always uses a plain StreamHandler (even in TTY)
                    to preserve exact format control (e.g. subagent_cli %(message)s).
    """
    global _logging_configured

    # Only configure once (idempotency)
    if _logging_configured:
        return

    # Determine log level (debug > quiet > explicit > env > default)
    if debug:
        log_level = logging.DEBUG
    elif quiet:
        log_level = logging.WARNING
    elif level:
        log_level = getattr(logging, level.upper(), logging.INFO)
    else:
        env_level = os.environ.get("VAULTSPEC_LOG_LEVEL", "INFO").upper()
        if not hasattr(logging, env_level):
            msg = f"Unknown VAULTSPEC_LOG_LEVEL={env_level!r}"
            print(f"Warning: {msg}, defaulting to INFO", file=sys.stderr)
        log_level = getattr(logging, env_level, logging.INFO)

    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Build handler: Rich for interactive TTY, plain for pipes/CI/custom format
    if log_format is not None:
        # Explicit format requested (e.g. subagent_cli "%(message)s") — plain handler
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter(log_format))
    elif sys.stderr.isatty():
        from rich.logging import RichHandler

        handler = RichHandler(
            console=get_console(),
            rich_tracebacks=True,
            tracebacks_show_locals=debug,
            markup=False,
            show_path=debug,
            show_time=debug,
            show_level=debug,
        )
    else:
        fmt = _DEBUG_FORMAT if debug else "%(message)s"
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter(fmt))

    handler.setLevel(log_level)
    root_logger.addHandler(handler)

    _logging_configured = True


def reset_logging() -> None:
    """Reset logging configuration so configure_logging() can be called again.

    Intended for use in tests and CLI tools that need to reconfigure logging
    within a single process lifetime.
    """
    global _logging_configured
    _logging_configured = False
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(logging.WARNING)

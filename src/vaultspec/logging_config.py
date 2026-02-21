"""Central logging configuration for vaultspec.

This module provides a single, idempotent entry point for configuring logging
across the entire vaultspec codebase.
"""

import logging
import os
import sys

__all__ = ["configure_logging", "reset_logging"]

# Module-level flag to ensure idempotency
_logging_configured = False


def configure_logging(
    level: str | None = None, debug: bool = False, log_format: str | None = None
) -> None:
    """Configure logging for vaultspec.

    This function is idempotent and safe to call multiple times.

    Args:
        level: Optional log level override (DEBUG, INFO, WARNING, ERROR, CRITICAL).
               If None, reads from VAULTSPEC_LOG_LEVEL env var, defaults to INFO.
        debug: If True, forces log level to DEBUG. Overrides level param.
        log_format: Optional format string for the log handler.
                    Defaults to "%(asctime)s [%(name)s] %(levelname)s: %(message)s".
    """
    global _logging_configured

    # Only configure once (idempotency)
    if _logging_configured:
        return

    # Determine log level
    if debug:
        log_level = logging.DEBUG
    elif level:
        log_level = getattr(logging, level.upper(), logging.INFO)
    else:
        env_level = os.environ.get("VAULTSPEC_LOG_LEVEL", "INFO").upper()
        log_level = getattr(logging, env_level, logging.INFO)

    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Create and configure handler
    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(log_level)

    # Set format
    fmt_string = log_format or "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
    formatter = logging.Formatter(fmt_string)
    handler.setFormatter(formatter)

    # Add handler to root logger
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

"""Central logging configuration for vaultspec.

This module provides a single, idempotent entry point for configuring logging
across the entire vaultspec codebase.
"""

import logging
import os
import sys

# Module-level flag to ensure idempotency
_logging_configured = False


def configure_logging(level: str | None = None, debug: bool = False) -> None:
    """Configure logging for vaultspec.

    This function is idempotent and safe to call multiple times.

    Args:
        level: Optional log level override (DEBUG, INFO, WARNING, ERROR, CRITICAL).
               If None, reads from VAULTSPEC_LOG_LEVEL env var, defaults to INFO.
        debug: If True, forces log level to DEBUG. Overrides level param.
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
    formatter = logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s")
    handler.setFormatter(formatter)

    # Add handler to root logger
    root_logger.addHandler(handler)

    _logging_configured = True

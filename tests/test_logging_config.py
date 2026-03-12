"""Tests for the logging_config module.

Covers: default configuration, debug override, explicit level,
        idempotency, VAULTSPEC_LOG_LEVEL env var, handler presence,
        and _configured flag behavior.
"""

from __future__ import annotations

import logging
import os

import pytest
from rich.logging import RichHandler

import vaultspec_core.logging_config as logging_config

pytestmark = [pytest.mark.unit]


@pytest.fixture(autouse=True)
def _reset_logging():
    """Reset logging state before and after each test."""
    logging_config.reset_logging()
    root = logging.getLogger()
    original_handlers = root.handlers[:]
    original_level = root.level
    yield
    logging_config.reset_logging()
    root.handlers = original_handlers
    root.setLevel(original_level)


# ===================================================================
# Default configuration
# ===================================================================


class TestDefaultConfiguration:
    """Test configure_logging() called with no arguments."""

    def test_default_sets_info_level(self):
        """Default (no args, no env) should set INFO level on root logger."""
        old = os.environ.pop("VAULTSPEC_LOG_LEVEL", None)
        try:
            logging_config.configure_logging()
            assert logging.getLogger().level == logging.INFO
        finally:
            if old is not None:
                os.environ["VAULTSPEC_LOG_LEVEL"] = old

    def test_default_adds_rich_handler(self):
        """configure_logging() should install exactly one RichHandler."""
        old = os.environ.pop("VAULTSPEC_LOG_LEVEL", None)
        try:
            logging_config.configure_logging()
            root = logging.getLogger()
            assert len(root.handlers) == 1
            assert isinstance(root.handlers[0], RichHandler)
        finally:
            if old is not None:
                os.environ["VAULTSPEC_LOG_LEVEL"] = old

    def test_default_sets_configured_flag(self):
        """After configure_logging(), _configured flag should be True."""
        old = os.environ.pop("VAULTSPEC_LOG_LEVEL", None)
        try:
            assert logging_config._configured is False
            logging_config.configure_logging()
            assert logging_config._configured is True
        finally:
            if old is not None:
                os.environ["VAULTSPEC_LOG_LEVEL"] = old


# ===================================================================
# debug=True override
# ===================================================================


class TestDebugOverride:
    """Test configure_logging(debug=True)."""

    def test_debug_forces_debug_level(self):
        """debug=True should force root logger to DEBUG level."""
        logging_config.configure_logging(debug=True)
        assert logging.getLogger().level == logging.DEBUG

    def test_debug_overrides_level_param(self):
        """debug=True should override an explicit level='WARNING'."""
        logging_config.configure_logging(level="WARNING", debug=True)
        assert logging.getLogger().level == logging.DEBUG


# ===================================================================
# Explicit level parameter
# ===================================================================


class TestExplicitLevel:
    """Test configure_logging(level=...) parameter."""

    def test_warning_level(self):
        logging_config.configure_logging(level="WARNING")
        assert logging.getLogger().level == logging.WARNING

    def test_error_level(self):
        logging_config.configure_logging(level="ERROR")
        assert logging.getLogger().level == logging.ERROR

    def test_critical_level(self):
        logging_config.configure_logging(level="CRITICAL")
        assert logging.getLogger().level == logging.CRITICAL

    def test_case_insensitive_level(self):
        logging_config.configure_logging(level="warning")
        assert logging.getLogger().level == logging.WARNING


# ===================================================================
# Idempotency
# ===================================================================


class TestIdempotency:
    """Test that configure_logging is idempotent."""

    def test_second_call_is_noop(self):
        """Calling configure_logging twice should NOT add duplicate handlers."""
        logging_config.configure_logging()
        root = logging.getLogger()
        count_after_first = len(root.handlers)
        logging_config.configure_logging()
        assert len(root.handlers) == count_after_first, (
            "Second call added duplicate handler"
        )

    def test_configured_flag_prevents_reconfiguration(self):
        """Once configured, a second call with different level must not change handlers."""
        logging_config.configure_logging()
        root = logging.getLogger()
        before = len(root.handlers)
        logging_config.configure_logging(level="DEBUG")
        assert len(root.handlers) == before


# ===================================================================
# VAULTSPEC_LOG_LEVEL environment variable
# ===================================================================


class TestEnvVar:
    """Test VAULTSPEC_LOG_LEVEL environment variable."""

    def test_env_var_warning(self):
        old = os.environ.get("VAULTSPEC_LOG_LEVEL")
        os.environ["VAULTSPEC_LOG_LEVEL"] = "WARNING"
        try:
            logging_config.configure_logging()
            assert logging.getLogger().level == logging.WARNING
        finally:
            if old is None:
                os.environ.pop("VAULTSPEC_LOG_LEVEL", None)
            else:
                os.environ["VAULTSPEC_LOG_LEVEL"] = old

    def test_env_var_debug(self):
        old = os.environ.get("VAULTSPEC_LOG_LEVEL")
        os.environ["VAULTSPEC_LOG_LEVEL"] = "DEBUG"
        try:
            logging_config.configure_logging()
            assert logging.getLogger().level == logging.DEBUG
        finally:
            if old is None:
                os.environ.pop("VAULTSPEC_LOG_LEVEL", None)
            else:
                os.environ["VAULTSPEC_LOG_LEVEL"] = old

    def test_explicit_level_overrides_env(self):
        """Explicit level= param should take precedence over env var."""
        old = os.environ.get("VAULTSPEC_LOG_LEVEL")
        os.environ["VAULTSPEC_LOG_LEVEL"] = "WARNING"
        try:
            logging_config.configure_logging(level="ERROR")
            assert logging.getLogger().level == logging.ERROR
        finally:
            if old is None:
                os.environ.pop("VAULTSPEC_LOG_LEVEL", None)
            else:
                os.environ["VAULTSPEC_LOG_LEVEL"] = old


# ===================================================================
# Handler type and level
# ===================================================================


class TestHandlerProperties:
    """Test properties of the installed handler."""

    def test_handler_is_rich_handler(self):
        """configure_logging() should install a RichHandler."""
        logging_config.configure_logging()
        root = logging.getLogger()
        assert len(root.handlers) == 1
        assert isinstance(root.handlers[0], RichHandler)

    def test_handler_level_matches_root(self):
        """The handler's level should match the root logger's level."""
        logging_config.configure_logging(level="WARNING")
        root = logging.getLogger()
        handler = root.handlers[-1]
        assert handler.level == logging.WARNING

    def test_configure_clears_existing_handlers(self):
        """configure_logging() removes pre-existing handlers before adding its own."""
        root = logging.getLogger()
        dummy = logging.StreamHandler()
        root.addHandler(dummy)
        before = len(root.handlers)
        assert before >= 1

        logging_config.configure_logging()
        # All previous handlers cleared, exactly 1 RichHandler remains
        assert len(root.handlers) == 1
        assert isinstance(root.handlers[0], RichHandler)


# ===================================================================
# Invalid level string
# ===================================================================


class TestInvalidLevel:
    """Test behavior with invalid level strings."""

    def test_invalid_level_falls_back_to_info(self):
        """An unrecognized level string should fall back to INFO."""
        logging_config.configure_logging(level="NONEXISTENT")
        assert logging.getLogger().level == logging.INFO

    def test_invalid_env_var_falls_back_to_info(self):
        """An unrecognized VAULTSPEC_LOG_LEVEL should fall back to INFO."""
        old = os.environ.get("VAULTSPEC_LOG_LEVEL")
        os.environ["VAULTSPEC_LOG_LEVEL"] = "BOGUS"
        try:
            logging_config.configure_logging()
            assert logging.getLogger().level == logging.INFO
        finally:
            if old is None:
                os.environ.pop("VAULTSPEC_LOG_LEVEL", None)
            else:
                os.environ["VAULTSPEC_LOG_LEVEL"] = old

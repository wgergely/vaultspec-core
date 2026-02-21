"""Tests for the logging_config module.

Covers: default configuration, debug override, explicit level,
        idempotency, VAULTSPEC_LOG_LEVEL env var, stderr handler,
        invalid level string, and _logging_configured flag behavior.
"""

from __future__ import annotations

import logging
import sys

import pytest

import vaultspec.logging_config as logging_config

pytestmark = [pytest.mark.unit]


@pytest.fixture(autouse=True)
def _reset_logging():
    """Reset logging state before and after each test.

    Uses the public reset_logging() API to clear module state and
    restores the root logger to its original handler state.
    """
    logging_config.reset_logging()
    root = logging.getLogger()
    original_handlers = root.handlers[:]
    original_level = root.level
    yield
    logging_config.reset_logging()
    # Restore original handler state
    root.handlers = original_handlers
    root.setLevel(original_level)


# ===================================================================
# Default configuration
# ===================================================================


class TestDefaultConfiguration:
    """Test configure_logging() called with no arguments."""

    def test_default_sets_info_level(self, monkeypatch):
        """Default (no args, no env) should set INFO level on root logger."""
        monkeypatch.delenv("VAULTSPEC_LOG_LEVEL", raising=False)
        logging_config.configure_logging()
        root = logging.getLogger()
        assert root.level == logging.INFO

    def test_default_adds_handler(self, monkeypatch):
        """Default call should add exactly one handler to root logger."""
        monkeypatch.delenv("VAULTSPEC_LOG_LEVEL", raising=False)
        root = logging.getLogger()
        before = len(root.handlers)
        logging_config.configure_logging()
        assert len(root.handlers) == before + 1

    def test_default_sets_configured_flag(self, monkeypatch):
        """After configure_logging(), _logging_configured should be True."""
        monkeypatch.delenv("VAULTSPEC_LOG_LEVEL", raising=False)
        assert logging_config._logging_configured is False
        logging_config.configure_logging()
        assert logging_config._logging_configured is True


# ===================================================================
# debug=True override
# ===================================================================


class TestDebugOverride:
    """Test configure_logging(debug=True)."""

    def test_debug_forces_debug_level(self):
        """debug=True should force root logger to DEBUG level."""
        logging_config.configure_logging(debug=True)
        root = logging.getLogger()
        assert root.level == logging.DEBUG

    def test_debug_overrides_level_param(self):
        """debug=True should override an explicit level='WARNING'."""
        logging_config.configure_logging(level="WARNING", debug=True)
        root = logging.getLogger()
        assert root.level == logging.DEBUG


# ===================================================================
# Explicit level parameter
# ===================================================================


class TestExplicitLevel:
    """Test configure_logging(level=...) parameter."""

    def test_warning_level(self):
        """level='WARNING' should set WARNING on root logger."""
        logging_config.configure_logging(level="WARNING")
        root = logging.getLogger()
        assert root.level == logging.WARNING

    def test_error_level(self):
        """level='ERROR' should set ERROR on root logger."""
        logging_config.configure_logging(level="ERROR")
        root = logging.getLogger()
        assert root.level == logging.ERROR

    def test_critical_level(self):
        """level='CRITICAL' should set CRITICAL on root logger."""
        logging_config.configure_logging(level="CRITICAL")
        root = logging.getLogger()
        assert root.level == logging.CRITICAL

    def test_case_insensitive_level(self):
        """Level strings should be case-insensitive."""
        logging_config.configure_logging(level="warning")
        root = logging.getLogger()
        assert root.level == logging.WARNING


# ===================================================================
# Idempotency
# ===================================================================


class TestIdempotency:
    """Test that configure_logging is idempotent."""

    def test_second_call_is_noop(self):
        """Calling configure_logging twice should NOT add duplicate handlers."""
        root = logging.getLogger()
        before = len(root.handlers)
        logging_config.configure_logging()
        after_first = len(root.handlers)
        assert after_first == before + 1

        logging_config.configure_logging()
        after_second = len(root.handlers)
        assert after_second == after_first, "Second call added duplicate handler"

    def test_configured_flag_prevents_reconfiguration(self):
        """Once configured, a second call with different args must not add a handler."""
        logging_config.configure_logging()
        root = logging.getLogger()
        before = len(root.handlers)
        logging_config.configure_logging(level="DEBUG")
        after = len(root.handlers)
        assert after == before, "Should not add handler when already configured"


# ===================================================================
# VAULTSPEC_LOG_LEVEL environment variable
# ===================================================================


class TestEnvVar:
    """Test VAULTSPEC_LOG_LEVEL environment variable."""

    def test_env_var_warning(self, monkeypatch):
        """VAULTSPEC_LOG_LEVEL=WARNING should set WARNING level."""
        monkeypatch.setenv("VAULTSPEC_LOG_LEVEL", "WARNING")
        logging_config.configure_logging()
        root = logging.getLogger()
        assert root.level == logging.WARNING

    def test_env_var_debug(self, monkeypatch):
        """VAULTSPEC_LOG_LEVEL=DEBUG should set DEBUG level."""
        monkeypatch.setenv("VAULTSPEC_LOG_LEVEL", "DEBUG")
        logging_config.configure_logging()
        root = logging.getLogger()
        assert root.level == logging.DEBUG

    def test_explicit_level_overrides_env(self, monkeypatch):
        """Explicit level= param should take precedence over env var."""
        monkeypatch.setenv("VAULTSPEC_LOG_LEVEL", "WARNING")
        logging_config.configure_logging(level="ERROR")
        root = logging.getLogger()
        assert root.level == logging.ERROR


# ===================================================================
# Handler stream (stderr)
# ===================================================================


class TestHandlerStream:
    """Test that the handler writes to stderr."""

    def test_handler_outputs_to_stderr(self):
        """The added handler should be a StreamHandler targeting stderr."""
        root = logging.getLogger()
        before_count = len(root.handlers)
        logging_config.configure_logging()

        # Find the newly added handler
        new_handlers = root.handlers[before_count:]
        assert len(new_handlers) == 1
        handler = new_handlers[0]

        assert isinstance(handler, logging.StreamHandler)
        assert handler.stream is sys.stderr

    def test_handler_has_formatter(self):
        """The handler should have a formatter with expected pattern."""
        root = logging.getLogger()
        before_count = len(root.handlers)
        logging_config.configure_logging()

        handler = root.handlers[before_count]
        fmt = handler.formatter
        assert fmt is not None
        # The format includes asctime, name, levelname, message
        format_str = fmt._fmt
        assert format_str is not None
        assert "%(asctime)s" in format_str
        assert "%(name)s" in format_str
        assert "%(levelname)s" in format_str
        assert "%(message)s" in format_str

    def test_handler_level_matches_root(self):
        """The handler's level should match the root logger's level."""
        logging_config.configure_logging(level="WARNING")
        root = logging.getLogger()
        # Get the last-added handler
        handler = root.handlers[-1]
        assert handler.level == logging.WARNING


# ===================================================================
# Invalid level string
# ===================================================================


class TestInvalidLevel:
    """Test behavior with invalid level strings."""

    def test_invalid_level_falls_back_to_info(self):
        """An unrecognized level string should fall back to INFO."""
        logging_config.configure_logging(level="NONEXISTENT")
        root = logging.getLogger()
        # getattr(logging, "NONEXISTENT", logging.INFO) returns INFO
        assert root.level == logging.INFO

    def test_invalid_env_var_falls_back_to_info(self, monkeypatch):
        """An unrecognized VAULTSPEC_LOG_LEVEL should fall back to INFO."""
        monkeypatch.setenv("VAULTSPEC_LOG_LEVEL", "BOGUS")
        logging_config.configure_logging()
        root = logging.getLogger()
        assert root.level == logging.INFO


# ===================================================================
# Log format parameter
# ===================================================================


class TestLogFormat:
    """Test configure_logging(log_format=...) parameter."""

    def test_custom_format(self):
        """Custom format string should be applied."""
        custom_fmt = "%(message)s"
        logging_config.configure_logging(log_format=custom_fmt)
        root = logging.getLogger()
        handler = root.handlers[-1]
        assert handler.formatter._fmt == custom_fmt

    def test_default_format(self):
        """Default format should be used if not provided."""
        logging_config.configure_logging()
        root = logging.getLogger()
        handler = root.handlers[-1]
        assert "%(asctime)s" in handler.formatter._fmt

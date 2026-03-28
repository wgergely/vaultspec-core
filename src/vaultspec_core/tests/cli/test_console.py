"""Tests for console singleton."""

from __future__ import annotations

import io

import pytest

from vaultspec_core.console import get_console, reset_console


@pytest.mark.unit
class TestConsole:
    def setup_method(self):
        reset_console()

    def test_console_singleton_returns_same_instance(self):
        c1 = get_console()
        c2 = get_console()
        assert c1 is c2

    def test_console_reset_creates_new_instance(self):
        c1 = get_console()
        reset_console()
        c2 = get_console()
        assert c1 is not c2

    def test_console_can_print_unicode(self, capsys):
        """Console must handle Unicode without UnicodeEncodeError."""
        console = get_console()
        # These are the exact characters that caused the cp1252 crash
        console.print("\u2713")  # check mark
        console.print("\u26a0")  # warning
        console.print("\u2588")  # full block
        console.print("\u2591")  # light shade
        # If we get here without UnicodeEncodeError, the test passes

    def test_safe_box_on_non_utf8_terminal(self, monkeypatch):
        """safe_box must be True when terminal encoding is not UTF-8."""
        fake_stdout = type(
            "FakeStdout",
            (),
            {"encoding": "cp1252", "buffer": io.BytesIO()},
        )()
        monkeypatch.setattr("vaultspec_core.console.sys.stdout", fake_stdout)
        reset_console()
        console = get_console()
        assert console.safe_box is True
        reset_console()

    def test_no_color_env_var(self, monkeypatch):
        """no_color must be True when NO_COLOR env var is set."""
        monkeypatch.setenv("NO_COLOR", "1")
        reset_console()
        console = get_console()
        assert console.no_color is True

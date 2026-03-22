"""Tests for console singleton."""

from unittest.mock import patch

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
        console.print("\u2713")  # ✓
        console.print("\u26a0")  # ⚠
        console.print("\u2588")  # █
        console.print("\u2591")  # ░
        # If we get here without UnicodeEncodeError, the test passes

    def test_safe_box_on_non_utf8_terminal(self):
        """safe_box must be True when terminal encoding is not UTF-8."""
        import io

        fake_stdout = type(
            "FakeStdout",
            (),
            {"encoding": "cp1252", "buffer": io.BytesIO()},
        )()
        with patch("vaultspec_core.console.sys") as mock_sys:
            mock_sys.stdout = fake_stdout
            mock_sys.stdout.encoding = "cp1252"
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

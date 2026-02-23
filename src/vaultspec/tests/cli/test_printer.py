"""Unit tests for vaultspec.printer.Printer.

All tests use StringIO-backed Console injection — no mocks, no patching.
The injection hook is Printer(stdout_console=..., stderr_console=...).
"""

from __future__ import annotations

import json
from io import StringIO

import pytest
from rich.console import Console

from vaultspec.printer import Printer

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_printer(quiet: bool = False) -> tuple[Printer, StringIO, StringIO]:
    """Return a Printer wired to in-memory buffers plus the buffers themselves."""
    out_buf = StringIO()
    err_buf = StringIO()
    printer = Printer(
        quiet=quiet,
        stdout_console=Console(file=out_buf, highlight=False, force_terminal=False),
        stderr_console=Console(file=err_buf, highlight=False, force_terminal=False),
    )
    return printer, out_buf, err_buf


# ---------------------------------------------------------------------------
# out()
# ---------------------------------------------------------------------------


class TestOut:
    """Printer.out() always writes to the stdout stream."""

    def test_out_writes_to_stdout(self):
        printer, out_buf, err_buf = make_printer(quiet=False)
        printer.out("hello stdout")
        assert "hello stdout" in out_buf.getvalue()
        assert err_buf.getvalue() == ""

    def test_out_not_suppressed_when_quiet(self):
        printer, out_buf, _ = make_printer(quiet=True)
        printer.out("still visible")
        assert "still visible" in out_buf.getvalue()


# ---------------------------------------------------------------------------
# out_json()
# ---------------------------------------------------------------------------


class TestOutJson:
    """Printer.out_json() emits valid JSON to the stdout stream."""

    def test_out_json_valid_json(self):
        printer, out_buf, err_buf = make_printer()
        data = {"key": "value", "count": 3}
        printer.out_json(data)
        raw = out_buf.getvalue()
        parsed = json.loads(raw)
        assert parsed == data
        assert err_buf.getvalue() == ""

    def test_out_json_list(self):
        printer, out_buf, _ = make_printer()
        printer.out_json([1, 2, 3])
        assert json.loads(out_buf.getvalue()) == [1, 2, 3]

    def test_out_json_not_suppressed_when_quiet(self):
        printer, out_buf, _ = make_printer(quiet=True)
        printer.out_json({"a": 1})
        assert json.loads(out_buf.getvalue()) == {"a": 1}


# ---------------------------------------------------------------------------
# status()
# ---------------------------------------------------------------------------


class TestStatus:
    """Printer.status() writes when quiet=False and is silent when quiet=True."""

    def test_status_writes_when_not_quiet(self):
        printer, out_buf, err_buf = make_printer(quiet=False)
        printer.status("indexing...")
        assert "indexing..." in err_buf.getvalue()
        assert out_buf.getvalue() == ""

    def test_status_silent_when_quiet(self):
        printer, out_buf, err_buf = make_printer(quiet=True)
        printer.status("this should be suppressed")
        assert err_buf.getvalue() == ""
        assert out_buf.getvalue() == ""


# ---------------------------------------------------------------------------
# warn()
# ---------------------------------------------------------------------------


class TestWarn:
    """Printer.warn() always writes to the stderr stream regardless of quiet."""

    def test_warn_writes_to_stderr(self):
        printer, out_buf, err_buf = make_printer(quiet=False)
        printer.warn("something is off")
        assert "something is off" in err_buf.getvalue()
        assert out_buf.getvalue() == ""

    def test_warn_not_suppressed_when_quiet(self):
        printer, _, err_buf = make_printer(quiet=True)
        printer.warn("still a warning")
        assert "still a warning" in err_buf.getvalue()


# ---------------------------------------------------------------------------
# error()
# ---------------------------------------------------------------------------


class TestError:
    """Printer.error() always writes to the stderr stream regardless of quiet."""

    def test_error_writes_to_stderr(self):
        printer, out_buf, err_buf = make_printer(quiet=False)
        printer.error("fatal problem")
        assert "fatal problem" in err_buf.getvalue()
        assert out_buf.getvalue() == ""

    def test_error_not_suppressed_when_quiet(self):
        printer, _, err_buf = make_printer(quiet=True)
        printer.error("still an error")
        assert "still an error" in err_buf.getvalue()


# ---------------------------------------------------------------------------
# Constructor defaults
# ---------------------------------------------------------------------------


class TestConstructorDefaults:
    """Verify that Printer() with no injection arguments constructs without error."""

    def test_default_construction(self):
        printer = Printer()
        assert printer.quiet is False

    def test_quiet_default_construction(self):
        printer = Printer(quiet=True)
        assert printer.quiet is True

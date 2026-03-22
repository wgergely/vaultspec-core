"""Provide the shared Rich console used for user-facing CLI output.

Configures safe_box and encoding to prevent Unicode crashes on Windows
terminals that use cp1252 or similar legacy codepages.
"""

from __future__ import annotations

import io
import os
import sys

from rich.console import Console

__all__ = ["get_console", "reset_console"]

_console: Console | None = None


def _is_utf8_capable() -> bool:
    """Check if stdout can handle UTF-8 output."""
    encoding = getattr(sys.stdout, "encoding", None) or ""
    return encoding.lower().replace("-", "") in ("utf8", "utf_8")


def _make_utf8_stdout() -> io.TextIOWrapper:
    """Wrap stdout's underlying byte buffer with a UTF-8 text wrapper.

    This avoids UnicodeEncodeError when Rich writes Unicode characters
    (such as check-marks and block elements) to a cp1252-encoded console.
    """
    return io.TextIOWrapper(
        sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True
    )


def get_console() -> Console:
    """Return the shared stdout Rich console singleton.

    On non-UTF-8 terminals, wraps stdout in a UTF-8 writer and enables
    safe_box to prevent UnicodeEncodeError from box-drawing and symbol
    characters.
    """
    global _console
    if _console is None:
        utf8 = _is_utf8_capable()
        kwargs: dict = {
            "highlight": False,
            "soft_wrap": True,
            "no_color": "NO_COLOR" in os.environ,
            "safe_box": not utf8,
        }
        if not utf8:
            kwargs["file"] = _make_utf8_stdout()
            kwargs["legacy_windows"] = False
        _console = Console(**kwargs)
    return _console


def reset_console() -> None:
    """Reset the stdout console singleton.

    Allows a fresh Console to be created on the next get_console() call.
    Primarily useful in tests that need a specific terminal width.
    """
    global _console
    _console = None

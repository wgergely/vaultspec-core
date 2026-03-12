"""Provide the shared Rich console used for user-facing CLI output.

This module defines the stdout-oriented console singleton used across the
vault/spec-core command surfaces to keep terminal presentation consistent.
"""

from __future__ import annotations

from rich.console import Console

__all__ = ["get_console", "reset_console"]

_console: Console | None = None


def get_console() -> Console:
    """Return the shared stdout Rich console singleton.

    No explicit ``file=`` is passed so Rich resolves ``sys.stdout`` dynamically
    at each ``print()`` call.  This means ``typer.testing.CliRunner``'s patched
    ``sys.stdout`` is used automatically during tests — no reset needed.

    Returns:
        The shared :class:`rich.console.Console` writing to ``stdout``.
    """
    global _console
    if _console is None:
        _console = Console(highlight=False, soft_wrap=True)
    return _console


def reset_console() -> None:
    """Reset the stdout console singleton.

    Allows a fresh :class:`~rich.console.Console` to be created on the next
    :func:`get_console` call.  Primarily useful in tests that need a specific
    terminal width.
    """
    global _console
    _console = None

"""Printer: dual-channel output router for vaultspec CLI commands.

Owns a stdout Console (program output, always emitted) and a stderr Console
(human-facing status, suppressible via ``quiet``).  Inject custom Console
instances via the constructor for test-time stream capture without mocking.
"""

from __future__ import annotations

import json
from typing import Any

from rich.console import Console

__all__ = ["Printer"]


class Printer:
    """Route program output to stdout and human messaging to stderr.

    Args:
        quiet: When ``True``, :meth:`status` calls are suppressed.
            ``out``, ``warn``, and ``error`` are never suppressed.
        stdout_console: Console writing to stdout.  Defaults to
            ``Console(stderr=False, highlight=False)``.
        stderr_console: Console writing to stderr.  Defaults to
            ``Console(stderr=True, highlight=False)``.
    """

    def __init__(
        self,
        quiet: bool = False,
        stdout_console: Console | None = None,
        stderr_console: Console | None = None,
    ) -> None:
        self.quiet = quiet
        self._out = (
            stdout_console
            if stdout_console is not None
            else Console(stderr=False, highlight=False)
        )
        self._err = (
            stderr_console
            if stderr_console is not None
            else Console(stderr=True, highlight=False)
        )

    def out(self, *args: Any, **kwargs: Any) -> None:
        """Print program output to stdout; never suppressed."""
        self._out.print(*args, **kwargs)

    def out_json(self, data: Any, *, indent: int = 2) -> None:
        """Serialize ``data`` as JSON and print to stdout; never suppressed.

        Writes directly to the Console's underlying file to bypass Rich's
        word-wrap, which would insert literal newlines into long JSON string
        values and break parsers.
        """
        f = self._out.file
        f.write(json.dumps(data, indent=indent))
        f.write("\n")
        f.flush()

    def status(self, msg: Any, *args: Any, **kwargs: Any) -> None:
        """Print a status message to stderr; suppressed when ``quiet=True``."""
        if not self.quiet:
            self._err.print(msg, *args, **kwargs)

    def warn(self, msg: Any, *args: Any, **kwargs: Any) -> None:
        """Print a warning to stderr with yellow bold style; never suppressed."""
        kwargs.setdefault("style", "yellow bold")
        self._err.print(msg, *args, **kwargs)

    def error(self, msg: Any, *args: Any, **kwargs: Any) -> None:
        """Print an error to stderr with red bold style; never suppressed."""
        kwargs.setdefault("style", "red bold")
        self._err.print(msg, *args, **kwargs)

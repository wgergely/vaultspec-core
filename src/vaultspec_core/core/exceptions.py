"""Domain exceptions for vaultspec-core business logic.

These exceptions decouple the core package from any specific CLI framework
(typer, click, argparse) so that the same business logic can be consumed by
CLI, MCP server, and programmatic callers without catching ``SystemExit``.
"""

from __future__ import annotations

from pathlib import Path


class VaultSpecError(Exception):
    """Base exception for all vaultspec-core domain errors.

    Attributes:
        hint: Optional actionable guidance shown below the error message in
            CLI and MCP output.
    """

    def __init__(self, message: str, *, hint: str = "") -> None:
        super().__init__(message)
        self.hint = hint


class ResourceNotFoundError(VaultSpecError):
    """A requested resource (rule, skill, agent, file) does not exist."""


class ResourceExistsError(VaultSpecError):
    """A resource already exists and --force was not specified."""


class ProviderError(VaultSpecError):
    """An invalid or unsupported provider was specified."""


class WorkspaceNotInitializedError(VaultSpecError):
    """The workspace has not been initialized (no .vaultspec/ directory)."""


class ProviderNotInstalledError(VaultSpecError):
    """A provider is not installed in the workspace manifest."""


class EditorResolutionError(VaultSpecError):
    """Failed to resolve a working text editor."""


class EditorSubprocessError(VaultSpecError):
    """The text editor subprocess failed or exited with a non-zero status."""


class EditorCancellationError(VaultSpecError):
    """The text editor edit was cancelled by the user."""


class AdvisoryLockTimeoutError(VaultSpecError):
    """An :func:`~vaultspec_core.core.helpers.advisory_lock` acquisition timed out.

    Deliberately **not** a subclass of :class:`TimeoutError`. ``TimeoutError``
    is an ``OSError``, and the write paths that take advisory locks are dotted
    with ``except OSError`` handlers that log a warning and continue - so
    inheriting from it would let the one failure this class exists to make
    visible be swallowed by a handler written for an unreadable file.

    Attributes:
        sentinel: The ``.lock`` file the acquisition was waiting on.
        timeout: The budget, in seconds, that was exhausted.
        layer: Which of the two layers gave up - ``"thread"`` for the
            in-process :class:`threading.Lock`, ``"os"`` for the cross-process
            file lock. The distinction narrows the diagnosis: the thread layer
            is the one a single-threaded lock cycle deadlocks on.
    """

    def __init__(
        self,
        sentinel: Path,
        timeout: float,
        layer: str,
        *,
        hint: str = "",
    ) -> None:
        super().__init__(
            f"Timed out after {timeout:g}s waiting for the advisory lock on "
            f"{sentinel} ({layer} layer).",
            hint=hint,
        )
        self.sentinel = sentinel
        self.timeout = timeout
        self.layer = layer

"""Domain exceptions for vaultspec-core business logic.

These exceptions decouple the core package from any specific CLI framework
(typer, click, argparse) so that the same business logic can be consumed by
CLI, MCP server, and programmatic callers without catching ``SystemExit``.
"""

from __future__ import annotations


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

"""Converge managed MCP launch entries to the current canonical shape.

Introduced for vaultspec-core 0.1.48. Earlier releases rendered the
dependency-mode MCP launch without the ``--no-sync`` guard, so a client
connect could trigger an implicit environment sync. The canonical shape
changed, but reconciliation skips a drifted managed entry unless the
operator passes ``--force``, so already-deployed workspaces would keep the
regressed launch indefinitely.

This migration re-renders every provider enrollment the workspace's
ownership sidecar records, at project scope, through the owning
:func:`~vaultspec_core.core.mcps.mcp_sync` verb. The fingerprint-verified
refresh path does the byte work: only entries that are provably untouched
since vaultspec wrote them converge, each narrated with an old-to-new
launch line in the sync result. Hand-edited entries, external entries, and
ownership records that predate fingerprinting are left exactly as the live
sync would leave them, with the same warnings.

A workspace with no recorded project-scope enrollment (for example one
provisioned with ``--skip mcp``) is a true no-op: the migration never
creates an enrollment the operator opted out of.

See also:
    :mod:`vaultspec_core.migrations` for the registry driver.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from . import Migration, MigrationResult, MigrationScope

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["MIGRATION", "migrate"]

logger = logging.getLogger(__name__)

_TARGET_VERSION = "0.1.48"
_NAME = "launch_convergence"


def migrate(workspace: Path) -> MigrationResult:
    """Re-render recorded project-scope MCP enrollments through ``mcp_sync``.

    Reads the project-scope ownership sidecar to learn which providers hold
    vaultspec-managed entries, then reconciles exactly those providers. The
    fingerprint-verified refresh path decides per entry whether convergence
    is safe; this migration adds no force semantics of its own.

    Args:
        workspace: Workspace root directory.

    Returns:
        :class:`MigrationResult` whose ``counts`` carries ``refreshed``
        (entries rewritten to the current shape), ``skipped`` (entries left
        for the operator, e.g. hand-edited), and ``providers`` (enrollments
        reconciled).

    Raises:
        Nothing beyond what the owning sync verb raises for real I/O
        failures; per-target parse problems are reported in the sync result
        and logged, matching the live ``sync`` behavior, so a broken host
        file never wedges the migration registry.
    """
    from ..core.enums import McpScope
    from ..core.mcps import mcp_sync, ownership_path, read_ownership

    ownership_file = ownership_path(workspace, McpScope.PROJECT)
    if not ownership_file.exists():
        return MigrationResult(
            name=_NAME,
            target_version=_TARGET_VERSION,
            summary="no recorded MCP enrollment; nothing to converge",
            counts={"refreshed": 0, "skipped": 0, "providers": 0},
        )

    try:
        state = read_ownership(ownership_file)
    except Exception as exc:  # report, never wedge the registry
        logger.warning("Cannot read MCP ownership state at %s: %s", ownership_file, exc)
        return MigrationResult(
            name=_NAME,
            target_version=_TARGET_VERSION,
            summary="ownership sidecar unreadable; left for spec doctor",
            counts={"refreshed": 0, "skipped": 0, "providers": 0},
        )

    providers_seen: set[str] = set()
    for record in state["targets"].values():
        if record.get("scope") != McpScope.PROJECT.value:
            continue
        provider_value = record.get("provider")
        if provider_value:
            providers_seen.add(str(provider_value))
    providers = sorted(providers_seen)
    if not providers:
        return MigrationResult(
            name=_NAME,
            target_version=_TARGET_VERSION,
            summary="no project-scope MCP enrollment recorded; nothing to converge",
            counts={"refreshed": 0, "skipped": 0, "providers": 0},
        )

    refreshed = 0
    skipped = 0
    reconciled = 0
    for provider in providers:
        result = mcp_sync(
            provider=provider,
            scope=McpScope.PROJECT,
            target_dir=workspace,
        )
        reconciled += 1
        refreshed += sum(1 for _name, action in result.items if action == "[REFRESH]")
        skipped += result.skipped
        for line in result.warnings:
            logger.info("%s", line)
        for line in result.errors:
            logger.warning("MCP convergence for provider '%s': %s", provider, line)

    if refreshed:
        summary = (
            f"refreshed {refreshed} managed MCP launch entr"
            f"{'y' if refreshed == 1 else 'ies'} to the current standard"
        )
    else:
        summary = "managed MCP launch entries already current"
    if skipped:
        summary += f"; {skipped} left untouched (hand-edited or unverifiable)"

    return MigrationResult(
        name=_NAME,
        target_version=_TARGET_VERSION,
        summary=summary,
        counts={"refreshed": refreshed, "skipped": skipped, "providers": reconciled},
    )


MIGRATION = Migration(
    target_version=_TARGET_VERSION,
    name=_NAME,
    migrate=migrate,
    # Re-renders managed MCP launch entries in host configuration.
    scope=MigrationScope.ENVIRONMENT,
)

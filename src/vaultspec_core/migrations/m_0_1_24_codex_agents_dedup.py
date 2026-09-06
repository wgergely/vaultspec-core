"""Remove duplicate Codex ``[agents.*]`` tables from ``.codex/config.toml``.

Introduced for vaultspec-core 0.1.24 as the migration counterpart of issue
#140. Pre-tag-system releases emitted the Codex agents region under a legacy
``# BEGIN/END VAULTSPEC MANAGED CODEX AGENTS`` sentinel (or as raw, unwrapped
tables). When a later release appends the current ``<vaultspec type="agents">``
managed block, the two regions collide: ``[agents.<name>]`` and
``[agents."<name>"]`` are the same TOML key, so the file fails ``taplo`` lint
with ``conflicting keys`` and blocks every commit in repos whose pre-commit
runs ``taplo`` over ``.codex/``.

This migration strips the stale duplicates that sit outside the managed block,
preferring the managed-block copy as canonical. It is conservative: an agent
table whose name is not also declared inside the managed block is left
untouched, and a workspace with no managed block (and hence no canonical set to
dedup against) is left for the next ``sync`` to regenerate.

See also:
    :mod:`vaultspec_core.migrations` for the registry driver.
    :func:`vaultspec_core.core.agents.sanitize_legacy_codex_agents` for the
    shared sanitiser the live sync path also calls.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from . import Migration, MigrationError, MigrationResult, MigrationScope

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["MIGRATION", "migrate"]

logger = logging.getLogger(__name__)

_TARGET_VERSION = "0.1.24"
_NAME = "codex_agents_dedup"


def migrate(workspace: Path) -> MigrationResult:
    """Strip duplicate Codex agent tables from ``<workspace>/.codex/config.toml``.

    Locates the managed ``<vaultspec type="agents">`` block, takes the agent
    names it declares as canonical, and removes any matching ``[agents.<name>]``
    table that lives outside the block (plus any legacy sentinel block). When
    the file is absent, has no managed block, or already carries no stale
    duplicates, the migration is a true no-op.

    Args:
        workspace: Workspace root directory.

    Returns:
        :class:`MigrationResult` whose ``counts`` carries the ``deduped`` flag.

    Raises:
        MigrationError: When ``.codex/config.toml`` cannot be read or written.
            The driver propagates the exception unchanged so the manifest
            version is not bumped and the next invocation retries.
    """
    from ..core.agents import (
        codex_managed_agent_names,
        sanitize_legacy_codex_agents,
    )
    from ..core.helpers import atomic_write

    counts = {"deduped": 0}

    config_path = workspace / ".codex" / "config.toml"
    if not config_path.exists():
        return MigrationResult(
            name=_NAME,
            target_version=_TARGET_VERSION,
            summary="no .codex/config.toml; nothing to migrate",
            counts=counts,
        )

    try:
        content = config_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise MigrationError(f"{_NAME}: failed to read {config_path}: {exc}") from exc

    names = codex_managed_agent_names(content)
    sanitized = sanitize_legacy_codex_agents(content, names)
    if sanitized == content:
        return MigrationResult(
            name=_NAME,
            target_version=_TARGET_VERSION,
            summary="no duplicate Codex agent tables; nothing to migrate",
            counts=counts,
        )

    try:
        atomic_write(config_path, sanitized)
    except OSError as exc:
        raise MigrationError(
            f"{_NAME}: failed to rewrite {config_path}: {exc}"
        ) from exc

    counts["deduped"] = 1
    summary = "removed duplicate Codex agent tables from .codex/config.toml"
    logger.info("Migration %s: %s", _NAME, summary)
    return MigrationResult(
        name=_NAME,
        target_version=_TARGET_VERSION,
        summary=summary,
        counts=counts,
    )


MIGRATION = Migration(
    target_version=_TARGET_VERSION,
    name=_NAME,
    migrate=migrate,
    # Rewrites .codex/config.toml. No .vault/ document is touched.
    scope=MigrationScope.ENVIRONMENT,
)

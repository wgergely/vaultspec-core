"""Reverse the managed gitignore block to the team-shared spec-layer policy.

Introduced for vaultspec-core 0.1.20 as the migration counterpart of the
``cli-spec-gitignore`` ADR. Pre-0.1.20 installs wrote a managed
``.gitignore`` block that blanket-ignored ``.vaultspec/``, ``.mcp.json``,
and the generated provider directories, hiding a project's authoritative
policy from teammates who clone it. The reversed policy
(:func:`vaultspec_core.core.gitignore.get_recommended_entries`) ignores
only genuine per-machine runtime by-products.

This migration rewrites an existing managed block to the reversed policy.
It is conservative: a block carrying any entry outside the known
pre-reversal vocabulary is treated as operator-customised and left
untouched, with a one-line notice, so a hand-edited policy is never
silently clobbered.

See also:
    :mod:`vaultspec_core.migrations` for the registry driver.
    :func:`vaultspec_core.core.gitignore.get_recommended_entries` for the
    reversed policy this migration installs.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from . import Migration, MigrationError, MigrationResult, MigrationScope

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["MIGRATION", "migrate"]

logger = logging.getLogger(__name__)

_TARGET_VERSION = "0.1.20"
_NAME = "gitignore_reversal"


def _old_policy_vocabulary() -> frozenset[str]:
    """Return every entry the pre-reversal managed block could contain.

    The reversed policy emits a strict subset of the old one - it only
    removes entries, never adds them. Any entry inside a managed block
    that falls outside this set is therefore an operator addition the
    migration must not clobber.
    """
    from ..core.enums import DirName, FileName

    # Runtime by-products - emitted by both the old and the reversed policy.
    # The set also covers entries later releases added to the reversed
    # policy (mcp-ownership.json), so a re-run over an already-reversed
    # block stays a no-op instead of reading its own output as operator
    # edits.
    vocabulary = {
        ".vaultspec/_snapshots/",
        ".vaultspec/*.lock",
        ".vaultspec/providers.json",
        ".vaultspec/mcp-ownership.json",
        ".vault/.obsidian/",
        ".vault/.trash/",
        ".vault/data/",
        ".vault/logs/",
        "/.gitignore.lock",
        "/.mcp.json.lock",
        "/.pre-commit-config.yaml.lock",
    }
    # Authored content the reversal stops ignoring.
    vocabulary.add(".vaultspec/")
    vocabulary.add(".mcp.json")
    for directory in (
        DirName.CLAUDE,
        DirName.GEMINI,
        DirName.ANTIGRAVITY,
        DirName.CODEX,
    ):
        vocabulary.add(f"{directory.value}/")
    for filename in (FileName.CLAUDE, FileName.GEMINI, FileName.AGENTS):
        vocabulary.add(filename.value)
    return frozenset(vocabulary)


def migrate(workspace: Path) -> MigrationResult:
    """Rewrite the managed gitignore block to the team-shared policy.

    Locates the single ``# >>> vaultspec-managed >>>`` block in
    ``<workspace>/.gitignore`` and, when every entry inside it belongs to
    the known pre-reversal vocabulary, rewrites the block via
    :func:`vaultspec_core.core.gitignore.ensure_gitignore_block` to the
    reversed policy. A block carrying any unrecognised entry is treated
    as operator-customised and left in place with an advisory summary;
    the operator reconciles the sharing policy by hand.

    Args:
        workspace: Workspace root directory.

    Returns:
        :class:`MigrationResult` whose ``counts`` carries ``rewritten``
        and ``skipped`` flags.

    Raises:
        MigrationError: When ``.gitignore`` cannot be read or rewritten.
            The driver propagates the exception unchanged so the
            manifest version is not bumped and the next invocation
            retries from the same starting version.
    """
    from ..core.enums import ManagedState
    from ..core.gitignore import (
        ensure_gitignore_block,
        find_markers,
        get_recommended_entries,
    )
    from ..core.rules import converge_spec_layer_gitignore

    counts = {"rewritten": 0, "skipped": 0, "nested_gitignore": 0}

    # The reversal's intent - stop hiding a project's authoritative policy from
    # teammates - also covers the nested .vaultspec/rules/rules/.gitignore, which
    # pre-0.1.20 un-tracked project-authored rule sources. Converge it here so an
    # upgrade repairs the drift, not only install --force (issue #124).
    rules_src_dir = workspace / ".vaultspec" / "rules" / "rules"
    if rules_src_dir.exists() and converge_spec_layer_gitignore(rules_src_dir):
        counts["nested_gitignore"] = 1

    gi_path = workspace / ".gitignore"
    if not gi_path.exists():
        return MigrationResult(
            name=_NAME,
            target_version=_TARGET_VERSION,
            summary="no .gitignore; nothing to migrate",
            counts=counts,
        )

    try:
        content = gi_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise MigrationError(f"{_NAME}: failed to read {gi_path}: {exc}") from exc

    lines = content.splitlines()
    begins, ends = find_markers(lines)
    if len(begins) != 1 or len(ends) != 1 or begins[0] >= ends[0]:
        # No single well-formed managed block: nothing this migration owns.
        return MigrationResult(
            name=_NAME,
            target_version=_TARGET_VERSION,
            summary="no managed gitignore block; nothing to migrate",
            counts=counts,
        )

    block_entries = [
        line.strip() for line in lines[begins[0] + 1 : ends[0]] if line.strip()
    ]
    foreign = sorted(e for e in block_entries if e not in _old_policy_vocabulary())
    if foreign:
        counts["skipped"] = 1
        logger.info(
            "Migration %s: managed block carries operator edits %s; left untouched",
            _NAME,
            foreign,
        )
        return MigrationResult(
            name=_NAME,
            target_version=_TARGET_VERSION,
            summary=(
                "managed gitignore block has operator edits; left "
                "untouched - reconcile the team-shared spec-layer "
                "policy manually"
            ),
            counts=counts,
        )

    try:
        changed = ensure_gitignore_block(
            workspace,
            get_recommended_entries(workspace),
            state=ManagedState.PRESENT,
        )
    except OSError as exc:
        raise MigrationError(f"{_NAME}: failed to rewrite {gi_path}: {exc}") from exc

    if changed:
        counts["rewritten"] = 1
        summary = (
            "rewrote the managed gitignore block to the team-shared spec-layer policy"
        )
    else:
        summary = "managed gitignore block already matches the team-shared policy"
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
    # Rewrites the managed .gitignore block. No .vault/ document is read
    # or written, and nothing about where an authored document lands
    # depends on it.
    scope=MigrationScope.ENVIRONMENT,
)

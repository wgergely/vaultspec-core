"""Relocate root-level ``<feature>.index.md`` files into ``.vault/index/``.

Introduced in vaultspec-core 0.1.17 as the structural counterpart to
the index-folder feature (PR #92, issue #91). Pre-0.1.17 vaults wrote
generated indexes directly under the docs root; the new layout dedicates
``<docs_dir>/<index_dir>/`` to them. This migration walks the docs tree,
relocates every ``*.index.md`` whose parent is not the configured index
subfolder, and inserts the ``#index`` directory tag into each migrated
file's frontmatter when missing.

The body is a near-verbatim port of the original
``_migrate_legacy_root_indexes`` helper shipped inside
``vaultspec_core.vaultcore.checks.structure``. CRLF line endings,
exact-match ``#index`` tag detection, and atomic-write semantics are
preserved.

See also:
    :mod:`vaultspec_core.migrations` for the registry driver.
    :mod:`vaultspec_core.vaultcore.checks.structure` for the warning
    branch that detects pending migrations without mutating.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ..core.helpers import atomic_write
from ..vaultcore.rename_engine import assert_within
from . import Migration, MigrationError, MigrationResult

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["MIGRATION", "migrate"]

logger = logging.getLogger(__name__)


def migrate(workspace: Path) -> MigrationResult:
    """Move legacy root-level index files into the configured index subfolder.

    Walks ``<workspace>/<docs_dir>/`` for every ``*.index.md`` file
    whose parent directory is not the configured index subfolder
    (``<docs_dir>/<index_dir>/``). For each such file:

    1. Reads the file as bytes so the line-ending convention survives
       the decode (Python's universal-newline handling on
       :func:`pathlib.Path.read_text` would clobber CRLF before the
       caller could see it).
    2. Calls
       :func:`vaultspec_core.vaultcore.checks.structure.ensure_index_directory_tag`
       to insert ``#index`` into the YAML ``tags:`` block when missing,
       preserving the file's existing newline convention.
    3. Atomically writes the rewritten content to the canonical
       location and unlinks the legacy source. When the tag block did
       not need rewriting the file is moved with
       :meth:`pathlib.Path.replace` for a single-syscall rename.

    A target-side collision (canonical file already exists) is resolved
    by deleting the misplaced generated index. Feature indexes are
    derived artifacts, so the migration must never force manual
    conflict resolution for their content.

    A symlinked candidate is skipped rather than adopted, and every
    destination is checked for containment in the docs tree before it is
    written or unlinked: a generated index is always a regular file inside
    the vault, and relocating anything else would import content from
    outside the workspace into the directory agents read.

    Args:
        workspace: Workspace root directory.

    Returns:
        :class:`MigrationResult` with ``counts`` carrying ``moved`` and
        ``tagged`` relocations plus ``removed`` generated duplicates.

    Raises:
        MigrationError: When a legacy file cannot be read or the
            relocation syscall fails. The driver propagates the
            exception unchanged so the manifest version is not bumped
            and the next invocation retries from the same starting
            version.
    """
    from ..config import get_config
    from ..vaultcore.checks.structure import ensure_index_directory_tag

    cfg = get_config()
    docs_dir = workspace / cfg.docs_dir
    counts = {"moved": 0, "tagged": 0, "removed": 0}
    if not docs_dir.is_dir():
        return MigrationResult(
            name="index_subfolder",
            target_version="0.1.17",
            summary="no .vault/ directory; nothing to migrate",
            counts=counts,
        )

    index_dir = docs_dir / cfg.index_dir
    legacy_files: list[Path] = []
    for item in sorted(docs_dir.rglob("*.index.md")):
        if item.parent == index_dir:
            continue
        if item.is_symlink():
            # `rglob` does not descend THROUGH a symlinked directory, but a
            # symlinked FILE still satisfies `is_file()` because that call
            # follows the link. Adopting one would relocate whatever it
            # points at into `.vault/index/` - either by copying its bytes
            # or by moving the link itself - and the index directory is read
            # back into an agent's context, so a migration would become the
            # step that pulls outside content in. A generated feature index
            # is never a link; skip it and say so.
            logger.warning(
                "Migration index_subfolder: skipping symlinked index %s; "
                "a generated feature index is always a regular file",
                item,
            )
            continue
        if item.is_file():
            legacy_files.append(item)
    if not legacy_files:
        return MigrationResult(
            name="index_subfolder",
            target_version="0.1.17",
            summary="no legacy indexes found; nothing to migrate",
            counts=counts,
        )

    # Create the destination once; every relocation lands here.
    index_dir.mkdir(parents=True, exist_ok=True)

    for legacy in legacy_files:
        target = index_dir / legacy.name
        # `legacy.name` is a filename read off the filesystem, not composed
        # from document content, so it cannot traverse - but the index
        # directory itself can be a link, and the destination is written to
        # and unlinked. Resolve both sides and refuse anything that lands
        # outside the docs tree.
        assert_within(docs_dir, target)

        if target.exists():
            try:
                legacy.unlink()
            except OSError as exc:
                raise MigrationError(
                    f"index_subfolder: failed to remove generated legacy "
                    f"index {legacy}: {exc}"
                ) from exc
            counts["removed"] += 1
            logger.info(
                "Migration index_subfolder: removed generated legacy index %s; "
                "canonical %s already exists",
                legacy,
                target,
            )
            continue

        try:
            raw = legacy.read_bytes()
            content = raw.decode("utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise MigrationError(
                f"index_subfolder: failed to read {legacy}: {exc}"
            ) from exc

        new_content, changed = ensure_index_directory_tag(content)
        try:
            if changed:
                atomic_write(target, new_content)
                legacy.unlink()
                counts["tagged"] += 1
            else:
                legacy.replace(target)
        except OSError as exc:
            raise MigrationError(
                f"index_subfolder: failed to relocate {legacy}: {exc}"
            ) from exc

        counts["moved"] += 1
        logger.info("Migration index_subfolder: %s -> %s", legacy, target)

    moved_count = counts["moved"]
    summary = (
        f"relocated {moved_count} feature index "
        f"{'file' if moved_count == 1 else 'files'} into "
        f"{cfg.docs_dir}/{cfg.index_dir}/"
    )
    if counts["tagged"]:
        summary += f" (added #index tag to {counts['tagged']})"
    if counts["removed"]:
        removed_count = counts["removed"]
        summary += (
            f" (removed {removed_count} generated "
            f"{'duplicate' if removed_count == 1 else 'duplicates'})"
        )

    return MigrationResult(
        name="index_subfolder",
        target_version="0.1.17",
        summary=summary,
        counts=counts,
    )


MIGRATION = Migration(
    target_version="0.1.17",
    name="index_subfolder",
    migrate=migrate,
)

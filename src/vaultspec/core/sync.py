"""File synchronization engine for vaultspec resource management."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from . import types as _t
from .helpers import atomic_write, ensure_dir
from .types import SyncResult

logger = logging.getLogger(__name__)


def sync_files(
    sources: dict[str, tuple[Path, dict[str, Any], str]],
    dest_dir: Path,
    transform_fn: Any,
    dest_path_fn: Any,
    prune: bool,
    dry_run: bool,
    label: str,
) -> SyncResult:
    """Sync a set of source files to a destination directory.

    For each source entry, calls ``transform_fn`` to produce the destination
    content and ``dest_path_fn`` to resolve the destination path, then writes
    atomically. Optionally prunes destination files that are no longer in
    *sources*.

    Args:
        sources: Mapping of resource name to ``(path, frontmatter, body)`` tuple.
        dest_dir: Directory to sync files into.
        transform_fn: Callable ``(tool, name, meta, body) -> str | None`` that
            returns transformed content, or ``None`` to skip the file.
        dest_path_fn: Callable ``(dest_dir, name) -> Path`` that resolves the
            destination file path.
        prune: If ``True``, delete destination ``.md`` files not present in
            *sources*.
        dry_run: If ``True``, log planned actions without writing or deleting.
        label: Human-readable label used in log messages.

    Returns:
        A :class:`SyncResult` tallying added, updated, pruned, skipped, and
        errored files.
    """
    result = SyncResult()
    ensure_dir(dest_dir)

    logger.info("  Syncing %s...", label)

    for name, meta_tuple in sources.items():
        _src_path, meta, body = meta_tuple
        dest_path = dest_path_fn(dest_dir, name)
        try:
            content = transform_fn(None, name, meta, body)
            if content is None:
                result.skipped += 1
                continue

            action = "[UPDATE]" if dest_path.exists() else "[ADD]"

            if dry_run:
                rel = dest_path.relative_to(_t.ROOT_DIR)
                logger.info("    %s %s", action, rel)
            else:
                ensure_dir(dest_path.parent)
                atomic_write(dest_path, content)

            if action == "[ADD]":
                result.added += 1
            else:
                result.updated += 1

        except Exception as e:
            result.errors.append(f"{name}: {e}")
            logger.error("    [ERROR] %s: %s", name, e, exc_info=True)

    # Prune
    if prune:
        source_names = set(sources.keys())
        if dest_dir.exists():
            for existing in dest_dir.glob("*.md"):
                if existing.name not in source_names:
                    rel = existing.relative_to(_t.ROOT_DIR)
                    if dry_run:
                        logger.info("    [PRUNE] %s", rel)
                    else:
                        existing.unlink()
                    result.pruned += 1

    return result


def _skill_dest_path(dest_dir: Path, name: str) -> Path:
    """Return the destination path for a skill's SKILL.md file.

    Args:
        dest_dir: Base skills directory for the target tool.
        name: Skill directory name (e.g. ``"vaultspec-execute"``).

    Returns:
        The full path ``dest_dir / name / SKILL.md``.
    """
    return dest_dir / name / "SKILL.md"


def sync_skills(
    sources: dict[str, tuple[Path, dict[str, Any], str]],
    skills_dir: Path,
    transform_fn: Any,
    prune: bool,
    dry_run: bool,
    label: str,
) -> SyncResult:
    """Sync skill definitions to a destination skills directory.

    Each skill is written to ``skills_dir/<name>/SKILL.md``. When *prune* is
    enabled, only ``vaultspec-*`` prefixed directories (and legacy flat files)
    that are no longer in *sources* are removed; non-managed skills are left
    untouched. Skills listed in ``PROTECTED_SKILLS`` are never pruned.

    Args:
        sources: Mapping of skill name to ``(path, frontmatter, body)`` tuple.
        skills_dir: Base directory that contains individual skill sub-directories.
        transform_fn: Callable ``(tool, name, meta, body) -> str | None`` that
            returns transformed content, or ``None`` to skip the skill.
        prune: If ``True``, remove stale ``vaultspec-*`` skill directories and
            legacy flat ``.md`` files.
        dry_run: If ``True``, log planned actions without writing or deleting.
        label: Human-readable label used in log messages.

    Returns:
        A :class:`SyncResult` tallying added, updated, pruned, skipped, and
        errored skills.
    """
    skill_dest_path = _skill_dest_path

    result = SyncResult()
    ensure_dir(skills_dir)

    logger.info("  Syncing %s...", label)

    for name, meta_tuple in sources.items():
        _src_path, meta, body = meta_tuple
        dest_path = skill_dest_path(skills_dir, name)
        try:
            content = transform_fn(None, name, meta, body)
            if content is None:
                result.skipped += 1
                continue

            action = "[UPDATE]" if dest_path.exists() else "[ADD]"

            if dry_run:
                try:
                    rel = dest_path.relative_to(_t.ROOT_DIR)
                except ValueError:
                    rel = dest_path
                logger.info("    %s %s", action, rel)
            else:
                ensure_dir(dest_path.parent)
                atomic_write(dest_path, content)

            if action == "[ADD]":
                result.added += 1
            else:
                result.updated += 1

        except Exception as e:
            result.errors.append(f"{name}: {e}")
            logger.error("    [ERROR] %s: %s", name, e, exc_info=True)

    # Prune: only prune vaultspec-* prefixed skill dirs and legacy flat files
    if prune:
        source_names = set(sources.keys())
        if skills_dir.exists():
            for item in skills_dir.iterdir():
                if item.name in _t.PROTECTED_SKILLS:
                    continue
                if not item.name.startswith("vaultspec-"):
                    continue

                # Prune directory if not in sources
                if item.is_dir():
                    if item.name not in source_names:
                        skill_md = item / "SKILL.md"
                        if skill_md.exists():
                            try:
                                rel = skill_md.relative_to(_t.ROOT_DIR)
                            except ValueError:
                                rel = skill_md
                            if dry_run:
                                logger.info("    [PRUNE] %s", rel)
                            else:
                                skill_md.unlink()
                                if not any(item.iterdir()):
                                    item.rmdir()
                            result.pruned += 1

                # Prune legacy flat file (vaultspec-*.md)
                elif item.is_file() and item.suffix == ".md":
                    try:
                        rel = item.relative_to(_t.ROOT_DIR)
                    except ValueError:
                        rel = item
                    if dry_run:
                        logger.info("    [PRUNE] %s (legacy)", rel)
                    else:
                        item.unlink()
                    result.pruned += 1

    return result


def print_summary(resource: str, result: SyncResult) -> None:
    """Print a one-line sync summary for a resource type.

    Args:
        resource: Human-readable resource label (e.g. ``"Rules"``).
        result: Completed sync result to summarize.
    """
    parts = []
    if result.added:
        parts.append(f"{result.added} added")
    if result.updated:
        parts.append(f"{result.updated} updated")
    if result.pruned:
        parts.append(f"{result.pruned} pruned")
    if result.skipped:
        parts.append(f"{result.skipped} skipped")
    if result.errors:
        parts.append(f"{len(result.errors)} errors")
    summary = ", ".join(parts) if parts else "no changes"
    print(f"  {resource}: {summary}")

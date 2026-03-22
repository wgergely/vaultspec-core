"""Synchronize managed vaultspec resources into tool-specific destinations.

This module contains the callback-driven sync engine used to project canonical
framework content into generated tool layouts. It handles destination path
resolution, atomic writes, pruning, and summary accounting for both flat file
surfaces and directory-shaped skill layouts.

Usage is typically through ``sync_to_all_tools()`` for cross-tool propagation
or ``sync_files()`` when a caller already knows the exact destination.
"""

from __future__ import annotations

import logging
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .helpers import atomic_write, ensure_dir
from .types import SyncResult

logger = logging.getLogger(__name__)


def _sync_supporting_files(
    src_dir: Path, dest_dir: Path, *, dry_run: bool = False
) -> None:
    """Copy non-entrypoint files from a source skill directory to its destination.

    Recursively mirrors every file in *src_dir* (except ``SKILL.md``, which
    is handled by the main sync loop) into *dest_dir*, preserving the
    relative directory structure.  Files are only overwritten when their
    content differs from the destination.

    Args:
        src_dir: Source skill directory (e.g.
            ``.vaultspec/rules/skills/vaultspec-documentation``).
        dest_dir: Destination skill directory (e.g.
            ``.claude/skills/vaultspec-documentation``).
        dry_run: When ``True``, skip all writes.
    """
    for src_file in sorted(src_dir.rglob("*")):
        if not src_file.is_file():
            continue
        # SKILL.md is already handled by the main sync loop.
        if src_file.name == "SKILL.md" and src_file.parent == src_dir:
            continue

        rel = src_file.relative_to(src_dir)
        dest_file = dest_dir / rel

        if dest_file.exists():
            try:
                if dest_file.read_bytes() == src_file.read_bytes():
                    continue
            except Exception:
                pass

        if not dry_run:
            ensure_dir(dest_file.parent)
            dest_file.write_bytes(src_file.read_bytes())


def sync_files(
    sources: dict[str, tuple[Path, dict[str, Any], str]],
    dest_dir: Path,
    transform_fn: Callable[[Any, str, dict[str, Any], str], str | None],
    dest_path_fn: Callable[[Path, str], Path],
    prune: bool = False,
    dry_run: bool = False,
    label: str = "",
    is_skill: bool = False,
) -> SyncResult:
    """Synchronize a collection of source documents to a destination directory.

    For each source, calls ``transform_fn`` to produce the destination
    content and ``dest_path_fn`` to resolve the destination path, then writes
    atomically. Optionally prunes destination files that are no longer in
    *sources*.

    Args:
        sources: Mapping of filename to (source_path, metadata, body) tuples.
        dest_dir: Root directory for the synced files.
        transform_fn: Callback taking (tool, name, meta, body) and returning
            transformed content string or ``None`` to skip.
        dest_path_fn: Callback taking (dest_dir, name) and returning the
            destination file path.
        prune: If ``True``, delete destination items not present in *sources*.
        dry_run: If ``True``, log planned actions without writing or deleting.
        label: Human-readable label used in log messages.
        is_skill: If ``True``, pruning iterates over directories instead of .md files.

    Returns:
        A :class:`SyncResult` tallying added, updated, pruned, skipped, and
        errored files.
    """
    result = SyncResult()
    if not dry_run:
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

            action = "[SKIP]"
            if not dest_path.exists():
                action = "[ADD]"
            else:
                try:
                    existing_content = dest_path.read_text(encoding="utf-8")
                    if existing_content != content:
                        action = "[UPDATE]"
                except Exception:
                    action = "[UPDATE]"

            if action != "[SKIP]":
                abs_path = str(dest_path).replace("\\", "/")
                if dry_run:
                    result.items.append((abs_path, action))
                else:
                    ensure_dir(dest_path.parent)
                    atomic_write(dest_path, content)

                if action == "[ADD]":
                    result.added += 1
                else:
                    result.updated += 1
            else:
                result.skipped += 1

            # For directory-shaped resources (skills), sync supporting files
            # alongside the main entrypoint (e.g. agents/, references/).
            if is_skill:
                src_skill_dir = _src_path.parent
                dest_skill_dir = dest_path.parent
                _sync_supporting_files(src_skill_dir, dest_skill_dir, dry_run=dry_run)

        except Exception as e:
            result.errors.append(f"{name}: {e}")
            logger.error("    [ERROR] %s: %s", name, e, exc_info=True)

    # Detect stale destination items and either prune or warn.
    source_names = set(sources.keys())
    if dest_dir.exists():
        items = list(dest_dir.iterdir())
        for item in items:
            is_stale = False
            if is_skill:
                is_stale = (
                    item.is_dir()
                    and (item / "SKILL.md").exists()
                    and item.name not in source_names
                )
            else:
                is_stale = (
                    item.is_file()
                    and item.suffix == ".md"
                    and item.name not in source_names
                    and not item.name.endswith("-system.builtin.md")
                )

            if not is_stale:
                continue

            abs_path = str(item).replace("\\", "/")
            if prune:
                if dry_run:
                    result.items.append((abs_path, "[DELETE]"))
                else:
                    if is_skill:
                        shutil.rmtree(item)
                    else:
                        item.unlink()
                result.pruned += 1
            else:
                # Not pruning  - emit a warning so the user knows.
                result.warnings.append(
                    f"Stale {label} file: {abs_path} "
                    f"(not in .vaultspec source, use --force to remove)"
                )

    return result


def _skill_dest_path(dest_dir: Path, name: str) -> Path:
    """Return the destination path for a skill's SKILL.md file."""
    return dest_dir / name / "SKILL.md"


def sync_skills(
    sources: dict[str, tuple[Path, dict[str, Any], str]],
    skills_dir: Path,
    transform_fn: Callable[[Any, str, dict[str, Any], str], str | None],
    prune: bool = False,
    dry_run: bool = False,
    label: str = "",
) -> SyncResult:
    """Synchronize skill definitions to a destination skills directory.

    Thin wrapper around :func:`sync_files` with ``is_skill=True``, which
    routes each skill's content to ``skill_name/SKILL.md`` and scopes
    pruning to ``vaultspec-*`` subdirectories.

    Args:
        sources: Skill resource map (directory name → path/meta/body tuple).
        skills_dir: Root skills destination directory.
        transform_fn: Content transform callback
            ``(tool, name, meta, body) → str | None``.
        prune: Remove ``vaultspec-*`` skill directories not in *sources*.
        dry_run: Log planned actions without writing.
        label: Human-readable label used in log messages.

    Returns:
        A :class:`SyncResult` tallying the sync outcome.
    """
    return sync_files(
        sources=sources,
        dest_dir=skills_dir,
        transform_fn=transform_fn,
        dest_path_fn=_skill_dest_path,
        prune=prune,
        dry_run=dry_run,
        label=label,
        is_skill=True,
    )


def sync_to_all_tools(
    sources: dict[str, tuple[Path, dict[str, Any], str]],
    dir_attr: str,
    transform_fn: Callable[[Any, str, dict[str, Any], str], str | None],
    label: str,
    prune: bool = False,
    dry_run: bool = False,
    dest_path_fn: Callable[[Path, str], Path] | None = None,
    is_skill: bool = False,
) -> SyncResult:
    """Sync *sources* to every configured tool destination and accumulate results.

    Iterates over all entries in :data:`_t.TOOL_CONFIGS`, skips those where
    the directory attribute named by *dir_attr* is ``None``, and delegates to
    :func:`sync_files` for each destination.

    Args:
        sources: Resource map as returned by ``collect_*`` helpers.
        dir_attr: Attribute name on :class:`ToolConfig` that holds the
            destination directory (e.g. ``"rules_dir"``, ``"skills_dir"``).
        transform_fn: Content transform callback
            ``(tool, name, meta, body) → str | None``.
        label: Human-readable resource label used in log and summary output.
        prune: Remove destination files that are no longer in *sources*.
        dry_run: Log planned actions without writing.
        dest_path_fn: Optional path resolver; defaults to ``dest_dir / name``.
        is_skill: When ``True``, pruning targets directories (skills layout).

    Returns:
        Accumulated :class:`SyncResult` across all tool destinations.
    """
    if dest_path_fn is None:
        dest_path_fn = lambda dest_dir, name: dest_dir / name  # noqa: E731

    from .manifest import installed_tool_configs

    total = SyncResult()
    for tool_type, cfg in installed_tool_configs().items():
        dest_dir = getattr(cfg, dir_attr)
        if dest_dir is None:
            continue
        result = sync_files(
            sources=sources,
            dest_dir=dest_dir,
            transform_fn=lambda _tool, n, m, b, _tt=tool_type: transform_fn(
                _tt, n, m, b
            ),
            dest_path_fn=dest_path_fn,
            prune=prune,
            dry_run=dry_run,
            label=f"{label} -> {tool_type.value}",
            is_skill=is_skill,
        )
        total.added += result.added
        total.updated += result.updated
        total.pruned += result.pruned
        total.skipped += result.skipped
        total.errors.extend(result.errors)
        total.items.extend(result.items)
        total.warnings.extend(result.warnings)

    return total


def format_summary(resource: str, result: SyncResult) -> str:
    """Format a one-line summary of a synchronization pass.

    Returns:
        A human-readable summary string (without Rich markup).
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
    return f"{resource}: {summary}"

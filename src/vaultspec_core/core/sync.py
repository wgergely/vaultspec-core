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

from . import types as _t
from .helpers import atomic_write, ensure_dir
from .types import SyncResult

logger = logging.getLogger(__name__)


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
                if dry_run:
                    rel = dest_path.relative_to(_t.TARGET_DIR)
                    logger.info("    %s %s", action, rel)
                else:
                    ensure_dir(dest_path.parent)
                    atomic_write(dest_path, content)

                if action == "[ADD]":
                    result.added += 1
                else:
                    result.updated += 1
            else:
                result.skipped += 1

        except Exception as e:
            result.errors.append(f"{name}: {e}")
            logger.error("    [ERROR] %s: %s", name, e, exc_info=True)

    # Prune
    if prune:
        source_names = set(sources.keys())
        if dest_dir.exists():
            # If it's a skill, we iterate over directories. Otherwise, over .md files.
            # We also skip 'protected' skills (those without the vaultspec- prefix)
            items = list(dest_dir.iterdir())
            for item in items:
                # Skill pruning logic: only prune vaultspec-* dirs not in sources
                if is_skill:
                    if (
                        item.is_dir()
                        and item.name.startswith("vaultspec-")
                        and item.name not in source_names
                    ):
                        rel = item.relative_to(_t.TARGET_DIR)
                        if dry_run:
                            logger.info("    [PRUNE] %s", rel)
                        else:
                            shutil.rmtree(item)
                        result.pruned += 1
                else:
                    # Default pruning: .md files not in sources
                    if (
                        item.is_file()
                        and item.suffix == ".md"
                        and item.name not in source_names
                    ):
                        rel = item.relative_to(_t.TARGET_DIR)
                        if dry_run:
                            logger.info("    [PRUNE] %s", rel)
                        else:
                            item.unlink()
                        result.pruned += 1

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
    """Synchronize a collection of skill definitions to a destination directory."""
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

    # Read manifest to determine which providers to sync
    from .manifest import read_manifest

    installed = read_manifest(_t.TARGET_DIR)

    total = SyncResult()
    for tool_type, cfg in _t.TOOL_CONFIGS.items():
        # Skip providers not in manifest (when manifest exists)
        if installed and cfg.name not in installed:
            continue
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

    print_summary(label, total)
    return total


def print_summary(resource: str, result: SyncResult) -> None:
    """Print a one-line summary of a synchronization pass."""
    from vaultspec_core.console import get_console

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
    get_console().print(f"  [bold]{resource}[/bold]: {summary}")

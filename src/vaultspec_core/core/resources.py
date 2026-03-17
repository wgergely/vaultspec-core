"""Provide shared CRUD-style file operations for managed markdown resources.

This module centralizes the common show, edit, remove, and rename behaviors
used by higher-level rule, skill, and agent management commands so those
surfaces can stay focused on resource-specific paths and transforms.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

import typer

from .helpers import _launch_editor, ensure_dir

logger = logging.getLogger(__name__)


def _resolve_path(name: str, base_dir: Path, is_dir: bool) -> tuple[str, Path]:
    """Resolve a resource name to its canonical name and file path.

    For flat resources (rules, agents): ``base_dir/name.md``
    For directory resources (skills): ``base_dir/name/SKILL.md``
    """
    if is_dir:
        dir_path = base_dir / name
        return name, dir_path / "SKILL.md"
    file_name = name if name.endswith(".md") else f"{name}.md"
    return file_name, base_dir / file_name


def resource_show(
    name: str, *, base_dir: Path, label: str, is_dir: bool = False
) -> None:
    """Read and print the contents of a resource file."""
    _canonical, file_path = _resolve_path(name, base_dir, is_dir)

    if not file_path.exists():
        logger.error("Error: %s '%s' not found.", label, name)
        raise typer.Exit(code=1)

    typer.echo(file_path.read_text(encoding="utf-8"))


def resource_edit(
    name: str, *, base_dir: Path, label: str, is_dir: bool = False
) -> None:
    """Open a resource file in the configured text editor."""
    _canonical, file_path = _resolve_path(name, base_dir, is_dir)

    if not file_path.exists():
        logger.error("Error: %s '%s' not found.", label, name)
        raise typer.Exit(code=1)

    from ..config import get_config

    editor = get_config().editor
    logger.info("Opening editor (%s) for %s...", editor, _canonical)
    try:
        _launch_editor(editor, str(file_path))
    except Exception as e:
        logger.error("Error opening editor: %s", e, exc_info=True)


def resource_remove(
    name: str,
    *,
    base_dir: Path,
    label: str,
    force: bool = False,
    is_dir: bool = False,
) -> None:
    """Delete a resource file (or directory) from disk, with optional confirmation."""
    _canonical, file_path = _resolve_path(name, base_dir, is_dir)

    # For directory resources, check the parent dir exists
    check_path = file_path.parent if is_dir else file_path
    if not check_path.exists():
        logger.error("Error: %s '%s' not found.", label, name)
        raise typer.Exit(code=1)

    if not force and not typer.confirm(
        f"Are you sure you want to remove {label} '{name}'?"
    ):
        return

    if is_dir:
        shutil.rmtree(check_path)
    else:
        file_path.unlink()
    logger.info("Removed %s: %s", label, name)


def resource_rename(
    old_name: str,
    new_name: str,
    *,
    base_dir: Path,
    label: str,
    is_dir: bool = False,
) -> None:
    """Rename a resource file or directory on disk."""
    if is_dir:
        old_path = base_dir / old_name
        new_path = base_dir / new_name
    else:
        old_file = old_name if old_name.endswith(".md") else f"{old_name}.md"
        new_file = new_name if new_name.endswith(".md") else f"{new_name}.md"
        old_path = base_dir / old_file
        new_path = base_dir / new_file

    if not old_path.exists():
        logger.error("Error: %s '%s' not found.", label, old_name)
        raise typer.Exit(code=1)

    if new_path.exists():
        logger.error("Error: Destination '%s' already exists.", new_name)
        raise typer.Exit(code=1)

    ensure_dir(base_dir)
    shutil.move(str(old_path), str(new_path))
    logger.info("Renamed %s '%s' to '%s'.", label, old_name, new_name)

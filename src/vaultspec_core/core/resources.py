"""Provide shared CRUD-style file operations for managed markdown resources.

This module centralizes the common show, edit, remove, and rename behaviors
used by higher-level rule, skill, and agent management commands so those
surfaces can stay focused on resource-specific paths and transforms.
"""

from __future__ import annotations

import logging
from pathlib import Path

import typer

from .helpers import _launch_editor, ensure_dir

logger = logging.getLogger(__name__)


def resource_show(name: str, *, base_dir: Path, label: str) -> None:
    """Read and print the contents of a resource file.

    Args:
        name: Resource name.
        base_dir: Base directory to look for the resource in.
        label: Human-readable type name for logging (e.g. ``"Rule"``).
    """
    file_name = name if name.endswith(".md") else f"{name}.md"
    file_path = base_dir / file_name

    if not file_path.exists():
        logger.error("Error: %s '%s' not found.", label, name)
        raise typer.Exit(code=1)

    typer.echo(file_path.read_text(encoding="utf-8"))


def resource_edit(name: str, *, base_dir: Path, label: str) -> None:
    """Open a resource file in the configured text editor.

    Args:
        name: Resource name.
        base_dir: Base directory to look for the resource in.
        label: Human-readable type name for logging (e.g. ``"Rule"``).
    """
    file_name = name if name.endswith(".md") else f"{name}.md"
    file_path = base_dir / file_name

    if not file_path.exists():
        logger.error("Error: %s '%s' not found.", label, name)
        raise typer.Exit(code=1)

    from ..config import get_config

    editor = get_config().editor
    logger.info("Opening editor (%s) for %s...", editor, file_name)
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
) -> None:
    """Delete a resource file from disk, with optional confirmation.

    Args:
        name: Resource name.
        base_dir: Base directory to look for the resource in.
        label: Human-readable type name for logging (e.g. ``"Rule"``).
        force: Whether to skip confirmation.
    """
    file_name = name if name.endswith(".md") else f"{name}.md"
    file_path = base_dir / file_name

    if not file_path.exists():
        logger.error("Error: %s '%s' not found.", label, name)
        raise typer.Exit(code=1)

    if not force and not typer.confirm(
        f"Are you sure you want to remove {label} '{file_name}'?"
    ):
        return

    file_path.unlink()
    logger.info("Removed %s: %s", label, file_name)


def resource_rename(
    old_name: str,
    new_name: str,
    *,
    base_dir: Path,
    label: str,
) -> None:
    """Rename a resource file on disk.

    Args:
        old_name: Current name.
        new_name: New name.
        base_dir: Base directory to look for the resource in.
        label: Human-readable type name for logging (e.g. ``"Rule"``).
    """
    old_file = old_name if old_name.endswith(".md") else f"{old_name}.md"
    new_file = new_name if new_name.endswith(".md") else f"{new_name}.md"

    old_path = base_dir / old_file
    new_path = base_dir / new_file

    if not old_path.exists():
        logger.error("Error: %s '%s' not found.", label, old_name)
        raise typer.Exit(code=1)

    if new_path.exists():
        logger.error("Error: Destination '%s' already exists.", new_file)
        raise typer.Exit(code=1)

    ensure_dir(base_dir)
    old_path.rename(new_path)
    logger.info("Renamed %s '%s' to '%s'.", label, old_file, new_file)

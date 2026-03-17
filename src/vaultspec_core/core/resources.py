"""Provide shared CRUD-style file operations for managed markdown resources.

This module centralizes the common show, edit, remove, and rename behaviors
used by higher-level rule, skill, and agent management commands so those
surfaces can stay focused on resource-specific paths and transforms.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from .exceptions import ResourceExistsError, ResourceNotFoundError
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
) -> str:
    """Read and return the contents of a resource file.

    Returns:
        The file content as a string.

    Raises:
        ResourceNotFoundError: If the resource does not exist.
    """
    _canonical, file_path = _resolve_path(name, base_dir, is_dir)

    if not file_path.exists():
        raise ResourceNotFoundError(f"{label} '{name}' not found.")

    return file_path.read_text(encoding="utf-8")


def resource_edit(
    name: str, *, base_dir: Path, label: str, is_dir: bool = False
) -> Path:
    """Open a resource file in the configured text editor.

    Returns:
        The path to the resource file that was opened.

    Raises:
        ResourceNotFoundError: If the resource does not exist.
    """
    _canonical, file_path = _resolve_path(name, base_dir, is_dir)

    if not file_path.exists():
        raise ResourceNotFoundError(f"{label} '{name}' not found.")

    from ..config import get_config

    editor = get_config().editor
    logger.info("Opening editor (%s) for %s...", editor, _canonical)
    try:
        _launch_editor(editor, str(file_path))
    except Exception as e:
        logger.error("Error opening editor: %s", e, exc_info=True)

    return file_path


def resource_remove(
    name: str,
    *,
    base_dir: Path,
    label: str,
    force: bool = False,
    is_dir: bool = False,
    confirm_fn: object | None = None,
) -> bool:
    """Delete a resource file (or directory) from disk, with optional confirmation.

    Args:
        confirm_fn: Optional callable ``(prompt: str) -> bool`` for interactive
            confirmation.  When ``None`` and ``force`` is ``False``, the
            removal is skipped (non-interactive callers should pass ``force=True``).

    Returns:
        ``True`` if the resource was removed, ``False`` if skipped.

    Raises:
        ResourceNotFoundError: If the resource does not exist.
    """
    _canonical, file_path = _resolve_path(name, base_dir, is_dir)

    # For directory resources, check the parent dir exists
    check_path = file_path.parent if is_dir else file_path
    if not check_path.exists():
        raise ResourceNotFoundError(f"{label} '{name}' not found.")

    if not force:
        if confirm_fn is None:
            return False
        # confirm_fn is a callable
        if not confirm_fn(f"Are you sure you want to remove {label} '{name}'?"):  # type: ignore[operator]
            return False

    if is_dir:
        shutil.rmtree(check_path)
    else:
        file_path.unlink()
    logger.info("Removed %s: %s", label, name)
    return True


def resource_rename(
    old_name: str,
    new_name: str,
    *,
    base_dir: Path,
    label: str,
    is_dir: bool = False,
) -> Path:
    """Rename a resource file or directory on disk.

    Returns:
        The new path after renaming.

    Raises:
        ResourceNotFoundError: If the source resource does not exist.
        ResourceExistsError: If the destination already exists.
    """
    if is_dir:
        old_path = base_dir / old_name
        new_path = base_dir / new_name
    else:
        old_file = old_name if old_name.endswith(".md") else f"{old_name}.md"
        new_file = new_name if new_name.endswith(".md") else f"{new_name}.md"
        old_path = base_dir / old_file
        new_path = base_dir / new_file

    if not old_path.exists():
        raise ResourceNotFoundError(f"{label} '{old_name}' not found.")

    if new_path.exists():
        raise ResourceExistsError(f"Destination '{new_name}' already exists.")

    ensure_dir(base_dir)
    shutil.move(str(old_path), str(new_path))
    logger.info("Renamed %s '%s' to '%s'.", label, old_name, new_name)
    return new_path

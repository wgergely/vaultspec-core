"""Provide shared CRUD-style file operations for managed markdown resources.

This module centralizes the common show, edit, remove, and rename behaviors
used by higher-level rule, skill, and agent management commands so those
surfaces can stay focused on resource-specific paths and transforms.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from .exceptions import ResourceExistsError, ResourceNotFoundError, VaultSpecError
from .helpers import ensure_dir, rmtree_robust

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
    if file_name.replace("\\", "/").startswith("project/"):
        return file_name, base_dir / file_name
    path = base_dir / file_name
    if not path.exists():
        project_path = base_dir / "project" / file_name
        if project_path.exists():
            return f"project/{file_name}", project_path
    return file_name, path


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
    name: str,
    *,
    base_dir: Path,
    label: str,
    is_dir: bool = False,
    editor: str | None = None,
) -> Path:
    """Open a resource file in the configured text editor.

    Returns:
        The path to the resource file that was opened.

    Raises:
        ResourceNotFoundError: If the resource does not exist.
        EditorResolutionError: If the editor cannot be resolved.
        EditorSubprocessError: If the editor fails to launch or exits with a
            non-zero status.
        EditorCancellationError: If the editor session was interrupted/cancelled.
    """
    from .editor import assert_interactive_editing_allowed
    from .exceptions import (
        EditorCancellationError,
        EditorSubprocessError,
    )
    from .local_config import resolve_editor

    # Before resolution, not after: an invocation with no terminal cannot open
    # an editor whatever the ladder would have produced, and refusing here
    # keeps the answer from depending on which editors happen to be installed.
    assert_interactive_editing_allowed()

    _canonical, file_path = _resolve_path(name, base_dir, is_dir)

    if not file_path.exists():
        raise ResourceNotFoundError(f"{label} '{name}' not found.")

    try:
        from .types import get_context

        target_dir = get_context().target_dir
    except Exception:
        target_dir = None

    resolved_editor = resolve_editor(editor, target_dir)

    logger.info("Opening editor (%s) for %s...", resolved_editor, _canonical)

    import subprocess

    from .editor import spawn_editor

    try:
        returncode = spawn_editor(resolved_editor, file_path)

        if returncode != 0:
            if returncode == 130:
                raise EditorCancellationError("Editor edit cancelled by user.")
            raise EditorSubprocessError(
                f"Editor exited with non-zero exit code {returncode}."
            )
    except KeyboardInterrupt as e:
        raise EditorCancellationError("Editor edit cancelled by user (Ctrl+C).") from e
    except (OSError, subprocess.SubprocessError) as e:
        raise EditorSubprocessError(
            f"Failed to launch or run editor {resolved_editor!r}: {e}",
            hint=(
                "Ensure the editor command is valid and the "
                "executable is present on your PATH."
            ),
        ) from e

    return file_path


def resource_remove(
    name: str,
    *,
    base_dir: Path,
    label: str,
    force: bool = False,
    is_dir: bool = False,
    confirm_fn: Callable[[str], bool] | None = None,
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
        confirmed = confirm_fn(f"Are you sure you want to remove {label} '{name}'?")
        if not confirmed:
            return False

    if is_dir:
        rmtree_robust(check_path)
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
    """Rename a resource on disk atomically across filename and frontmatter.

    The move is driven through a :class:`RenameTransaction` bound to the
    resource's own ``base_dir`` (the per-scan-group root, which may be a
    provider mirror) and serialized on the shared ``.vaultspec`` resource lock,
    so every endpoint is containment-checked, the rename is case-safe, and any
    mid-apply failure rolls the resource tree back byte-for-byte before the
    error propagates.  The observable contract is unchanged: the same new path
    is returned and the same error types are raised.

    Returns:
        The new path after renaming.

    Raises:
        ResourceNotFoundError: If the source resource does not exist.
        ResourceExistsError: If the destination already exists.
        VaultSpecError: If an endpoint escapes ``base_dir``, the frontmatter
            cannot be parsed, or the on-disk rename fails.
    """
    from ..vaultcore import parse_frontmatter
    from ..vaultcore.rename_engine import (
        RenameTransaction,
        assert_within,
        resource_lock_target,
    )
    from .helpers import atomic_write, build_file
    from .types import get_context

    def _get_frontmatter_name(name_str: str) -> str:
        stem = name_str
        if stem.endswith(".md"):
            stem = stem[:-3]
        if stem.endswith(".builtin"):
            stem = stem[:-8]
        return stem

    # Serialize every resource mutator on the one shared ``.vaultspec`` sentinel
    # regardless of whether ``base_dir`` is the source tree or a provider mirror.
    # When no workspace context is active (a direct unit-test call), run
    # lock-free; ``advisory_lock`` no-ops anyway when the sentinel's parent dir
    # is absent.
    try:
        lock_target: Path | None = resource_lock_target(
            get_context().rules_src_dir.parent.parent
        )
    except LookupError:
        lock_target = None

    if is_dir:
        old_path = base_dir / old_name
        new_path = base_dir / new_name

        # Contain the directory endpoints (not just SKILL.md) before any work.
        assert_within(base_dir, old_path)
        assert_within(base_dir, new_path)

        if not old_path.exists():
            raise ResourceNotFoundError(f"{label} '{old_name}' not found.")

        old_file = old_path / "SKILL.md"
        if not old_file.exists():
            raise ResourceNotFoundError(
                f"{label} '{old_name}' not found (SKILL.md missing)."
            )

        if new_path.exists():
            raise ResourceExistsError(f"Destination '{new_name}' already exists.")

        try:
            content = old_file.read_text(encoding="utf-8")
            fm, body = parse_frontmatter(content)
        except Exception as exc:
            raise VaultSpecError(
                f"Failed to parse frontmatter in {old_file}: {exc}"
            ) from exc

        fm["name"] = _get_frontmatter_name(new_name)
        new_content = build_file(fm, body)

        ensure_dir(base_dir)
        with RenameTransaction(base_dir, lock_target=lock_target) as tx:
            tx.snapshot([old_file])
            if not tx.rename(old_path, new_path):
                raise VaultSpecError(
                    f"Failed to rename {label.lower()} '{old_name}' to '{new_name}'."
                )
            new_skill_file = new_path / "SKILL.md"
            tx.record_created_file(new_skill_file)
            atomic_write(new_skill_file, new_content)

        logger.info("Renamed %s '%s' to '%s'.", label, old_name, new_name)
        return new_path

    else:
        _old_canonical, old_path = _resolve_path(old_name, base_dir, is_dir)
        new_file = new_name if new_name.endswith(".md") else f"{new_name}.md"
        # Always rename to the flat root: nested resource folders (e.g. a
        # legacy ``project/`` rule subdir) are not supported, so a rename also
        # de-nests rather than re-creating the nested location.
        new_path = base_dir / new_file

        assert_within(base_dir, old_path)
        assert_within(base_dir, new_path)

        if not old_path.exists():
            raise ResourceNotFoundError(f"{label} '{old_name}' not found.")

        if new_path.exists():
            raise ResourceExistsError(f"Destination '{new_name}' already exists.")

        try:
            content = old_path.read_text(encoding="utf-8")
            fm, body = parse_frontmatter(content)
        except Exception as exc:
            raise VaultSpecError(
                f"Failed to parse frontmatter in {old_path}: {exc}"
            ) from exc

        fm["name"] = _get_frontmatter_name(new_name)
        new_content = build_file(fm, body)

        ensure_dir(new_path.parent)
        with RenameTransaction(base_dir, lock_target=lock_target) as tx:
            tx.snapshot([old_path])
            if not tx.rename(old_path, new_path):
                raise VaultSpecError(
                    f"Failed to rename {label.lower()} '{old_name}' to '{new_name}'."
                )
            tx.record_created_file(new_path)
            atomic_write(new_path, new_content)

        logger.info("Renamed %s '%s' to '%s'.", label, old_name, new_name)
        return new_path

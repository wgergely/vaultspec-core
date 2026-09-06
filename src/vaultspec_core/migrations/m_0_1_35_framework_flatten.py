"""Flatten the redundant ``rules/`` wrapper inside the framework directory.

Introduced in vaultspec-core 0.1.35 as the structural counterpart to the
framework-dir-flatten feature. Pre-0.1.35 installs seeded builtin resources
under a doubled ``rules/`` parent (``.vaultspec/rules/rules/``,
``.vaultspec/rules/skills/``, and so on); the new layout seeds them directly
under the framework root (``.vaultspec/rules/``, ``.vaultspec/skills/``, ...).
This migration relocates each resource directory up one level and removes the
emptied wrapper.

This is the first registry entry to mutate the framework directory
(``.vaultspec/``) rather than ``.vault/`` content. Like every entry it runs
under the advisory lock the driver holds on ``providers.json`` and must not
re-enter that lock (no ``add_providers`` / ``write_manifest`` calls). The
install manifest records provider names, not resource paths, so it needs no
rewrite; the ``_snapshots/`` tree is already category-keyed
(``_snapshots/<category>/``) identically before and after the flatten, so it is
left untouched.

See also:
    :mod:`vaultspec_core.migrations` for the registry driver.
    :mod:`vaultspec_core.core.types` for the flattened path resolution.
"""

from __future__ import annotations

import logging
import shutil
from typing import TYPE_CHECKING

from . import Migration, MigrationError, MigrationResult

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["MIGRATION", "migrate"]

logger = logging.getLogger(__name__)

# Resource directories seeded into the framework root. Mirrors the subdirectory
# names of the bundled builtins package; the wrapper being removed nested each
# of these under a ``rules/`` parent.
_RESOURCE_DIRS = (
    "rules",
    "skills",
    "agents",
    "system",
    "templates",
    "hooks",
    "mcps",
    "reference",
)

# Temporary name used to dodge the wrapper/inner-``rules`` name collision while
# relocating ``.vaultspec/rules/rules`` onto ``.vaultspec/rules``.
_TMP_NAME = "__framework_flatten_tmp__"


def _is_nested(vaultspec_dir: Path) -> bool:
    """Return ``True`` when *vaultspec_dir* still carries the ``rules/`` wrapper.

    The pre-flatten wrapper holds the resource directories as children
    (``rules/skills``, ``rules/agents``, ...). The flattened layout's
    ``rules/`` directory holds rule files directly and never a resource-type
    subdirectory, so the presence of any such child is an unambiguous signal
    that the workspace has not yet been migrated.
    """
    wrapper = vaultspec_dir / "rules"
    if not wrapper.is_dir():
        return False
    return any((wrapper / name).is_dir() for name in _RESOURCE_DIRS)


def _move_tree(src: Path, dst: Path) -> None:
    """Move *src* onto *dst*, merging into an existing *dst* directory.

    A missing *dst* is satisfied with a single atomic rename. When *dst*
    already exists (a mixed or partially-migrated workspace), each child of
    *src* is merged in - recursing for subdirectories and overwriting
    colliding files - and the emptied *src* is removed. The framework
    directory is a single filesystem, so the renames stay atomic.

    Every mutation here is a MOVE, not a write, which is why these calls
    stay on :meth:`pathlib.Path.replace` rather than routing through the
    atomic writer. A rename replaces the destination *entry*; it never
    opens the destination and so never follows a symlink sitting there to
    clobber what it names. A symlinked child that is relocated stays a
    symlink and stays inside ``.vaultspec/``, where it was already being
    read before the move, so the migration neither creates nor widens an
    exposure - it only changes which managed directory the entry sits in.

    A colliding file is overwritten by the rename itself, with no preceding
    ``unlink``. :meth:`pathlib.Path.replace` overwrites an existing
    destination on both POSIX and Windows, so unlinking first bought
    nothing and cost the guarantee that matters here: between the unlink
    and the rename the destination is gone and the source has not moved, so
    an interruption in that window leaves neither file at the destination
    path - and ``.vaultspec/rules/``, ``skills/``, ``templates/`` and
    ``system/`` hold hand-authored, user-editable content.
    """
    if not dst.exists():
        src.replace(dst)
        return

    for child in sorted(src.iterdir()):
        target = dst / child.name
        if child.is_dir():
            _move_tree(child, target)
        else:
            child.replace(target)
    src.rmdir()


def migrate(workspace: Path) -> MigrationResult:
    """Relocate nested resource directories up to the framework root.

    For a workspace whose ``.vaultspec/rules/`` still wraps the resource
    directories, this moves every ``.vaultspec/rules/<resource>`` to
    ``.vaultspec/<resource>``. The inner ``rules`` directory collides with its
    own wrapper, so it is relocated through a temporary name after the other
    resource directories have been moved out and the emptied wrapper removed.

    The operation is idempotent: an already-flattened workspace (no
    resource-type subdirectory under ``rules/``) is a true no-op, and a
    partially-migrated workspace re-runs cleanly because each move is guarded on
    the source still existing.

    Args:
        workspace: Workspace root directory.

    Returns:
        :class:`MigrationResult` whose ``counts`` carry ``relocated`` (resource
        directories moved up) and ``wrapper_removed`` (0 or 1).

    Raises:
        MigrationError: When a relocation syscall fails. The driver propagates
            the exception unchanged so the manifest version is not bumped and
            the next invocation retries from the same starting version.
    """
    from ..config import get_config

    cfg = get_config()
    vaultspec_dir = workspace / cfg.framework_dir
    counts = {"relocated": 0, "wrapper_removed": 0}

    if not vaultspec_dir.is_dir() or not _is_nested(vaultspec_dir):
        return MigrationResult(
            name="framework_flatten",
            target_version="0.1.35",
            summary="framework dir already flat; nothing to migrate",
            counts=counts,
        )

    wrapper = vaultspec_dir / "rules"

    try:
        # 1. Move every non-``rules`` resource directory up first, so the
        #    wrapper is left holding at most its inner ``rules`` child.
        for name in _RESOURCE_DIRS:
            if name == "rules":
                continue
            src = wrapper / name
            if not src.is_dir():
                continue
            _move_tree(src, vaultspec_dir / name)
            counts["relocated"] += 1

        # 2. Resolve the wrapper/inner-``rules`` collision through a temporary
        #    name: stage the inner ``rules`` aside, drop the emptied wrapper,
        #    then settle the staged directory onto the freed ``rules`` path.
        inner = wrapper / "rules"
        if inner.is_dir():
            tmp = vaultspec_dir / _TMP_NAME
            if tmp.exists():
                shutil.rmtree(tmp)
            inner.replace(tmp)

            if _remove_if_empty(wrapper):
                counts["wrapper_removed"] = 1
                tmp.replace(wrapper)
            else:
                # The wrapper retained unexpected loose content; merge the
                # staged rule files back into it rather than discarding either.
                _move_tree(tmp, wrapper)
            counts["relocated"] += 1
        elif _remove_if_empty(wrapper):
            counts["wrapper_removed"] = 1
    except OSError as exc:
        raise MigrationError(
            f"framework_flatten: failed to relocate framework resources "
            f"under {wrapper}: {exc}"
        ) from exc

    relocated = counts["relocated"]
    summary = (
        f"flattened {relocated} resource "
        f"{'directory' if relocated == 1 else 'directories'} from "
        f"{cfg.framework_dir}/rules/ to {cfg.framework_dir}/"
    )

    return MigrationResult(
        name="framework_flatten",
        target_version="0.1.35",
        summary=summary,
        counts=counts,
    )


def _remove_if_empty(directory: Path) -> bool:
    """Remove *directory* when it is empty; return whether it was removed."""
    if not directory.is_dir():
        return False
    if any(directory.iterdir()):
        return False
    directory.rmdir()
    return True


MIGRATION = Migration(
    target_version="0.1.35",
    name="framework_flatten",
    migrate=migrate,
)

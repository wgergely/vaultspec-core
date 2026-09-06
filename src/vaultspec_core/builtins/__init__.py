"""Bundled builtin resources deployed during ``vaultspec-core install``.

Contains canonical rules, skills, agents, system prompts, templates, and hooks
seeded directly into ``.vaultspec/`` on first install. Consumed by
:mod:`vaultspec_core.cli.root` via :func:`seed_builtins` and :func:`list_builtins`.
Uses :mod:`importlib.resources` for package-relative file access.
"""

from __future__ import annotations

import logging
from importlib import resources
from pathlib import Path

from ..core.helpers import atomic_write_bytes

logger = logging.getLogger(__name__)

__all__ = [
    "builtins_root",
    "check_outdated",
    "list_builtins",
    "seed_builtins",
]


def builtins_root() -> Path:
    """Return the filesystem path to the bundled builtins directory."""
    return Path(str(resources.files(__package__)))


def seed_builtins(
    target_dir: Path, *, force: bool = False, dry_run: bool = False
) -> list[tuple[str, str]]:
    """Copy bundled builtins into a target ``.vaultspec/`` directory.

    Files that already exist are left untouched unless *force* is True.

    Args:
        target_dir: The ``.vaultspec/`` framework directory to populate.
        force: Overwrite existing files.
        dry_run: Classify every builtin without writing anything - used to
            preview an ``install --upgrade`` run.

    Returns:
        List of ``(relative_path, action)`` pairs for every builtin the
        call acted on (or would act on, under *dry_run*), where ``action``
        is ``[ADD]`` (newly written), ``[UPDATE]`` (overwritten with
        changed content) or ``[UNCHANGED]`` (already current). Builtins
        skipped because they exist and *force* is False are omitted.
    """
    src = builtins_root()
    results: list[tuple[str, str]] = []

    # Walk the bundled builtins tree
    for src_file in sorted(src.rglob("*")):
        if not src_file.is_file():
            continue
        # Skip Python package artifacts
        if src_file.name in ("__init__.py", "__pycache__") or "__pycache__" in str(
            src_file
        ):
            continue

        rel = src_file.relative_to(src)
        dest = target_dir / rel
        rel_str = str(rel).replace("\\", "/")

        if dest.exists() and not force:
            continue

        try:
            src_bytes = src_file.read_bytes()
        except OSError as exc:
            logger.warning("Failed to read builtin %s: %s", rel, exc)
            continue

        if not dest.exists():
            action = "[ADD]"
        else:
            try:
                action = "[UNCHANGED]" if dest.read_bytes() == src_bytes else "[UPDATE]"
            except OSError:
                action = "[UPDATE]"

        if action != "[UNCHANGED]" and not dry_run:
            try:
                dest.parent.mkdir(parents=True, exist_ok=True)
                # The bytes are already in hand from the change comparison
                # above, so seeding writes them through the shared atomic
                # writer instead of `shutil.copy2`. `copy2` opens the
                # destination for writing and therefore follows a symlink
                # sitting at that path, silently overwriting whatever it
                # names; the writer refuses a symlinked destination. Source
                # timestamps are not preserved, which nothing reads: a
                # seeded builtin's freshness is decided by comparing its
                # bytes, as it is three lines above.
                atomic_write_bytes(dest, src_bytes)
            except OSError as exc:
                logger.warning("Failed to seed %s: %s", rel, exc)
                continue
        results.append((rel_str, action))

    return results


def list_builtins() -> list[str]:
    """Return relative paths of all bundled builtin files.

    Returns:
        Sorted list of relative paths (forward-slash separated).
    """
    src = builtins_root()
    paths: list[str] = []
    for f in sorted(src.rglob("*")):
        if not f.is_file():
            continue
        if f.name in ("__init__.py", "__pycache__") or "__pycache__" in str(f):
            continue
        paths.append(str(f.relative_to(src)).replace("\\", "/"))
    return paths


def check_outdated(target_dir: Path) -> list[str]:
    """Compare bundled builtins against a deployed ``.vaultspec/`` tree.

    Returns:
        List of relative paths (forward-slash separated) present in the
        package but missing or content-different at the target.
    """
    src = builtins_root()
    outdated: list[str] = []
    for src_file in sorted(src.rglob("*")):
        if not src_file.is_file():
            continue
        if src_file.name in ("__init__.py", "__pycache__") or "__pycache__" in str(
            src_file
        ):
            continue
        rel = src_file.relative_to(src)
        dest = target_dir / rel
        if not dest.exists():
            outdated.append(str(rel).replace("\\", "/"))
            continue
        try:
            if src_file.read_bytes() != dest.read_bytes():
                outdated.append(str(rel).replace("\\", "/"))
        except OSError:
            outdated.append(str(rel).replace("\\", "/"))
    return outdated

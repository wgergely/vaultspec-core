"""Bundled builtin resources deployed during ``vaultspec-core install``.

This package contains the canonical source files for rules, skills, agents,
system prompts, templates, and hooks that are seeded into a fresh
``.vaultspec/rules/`` directory on install.
"""

from __future__ import annotations

import shutil
from importlib import resources
from pathlib import Path


def _builtins_root() -> Path:
    """Return the filesystem path to the bundled builtins directory."""
    ref = resources.files(__package__)
    # resources.files() returns a Traversable; on real installs this is
    # already a Path, but we cast to be safe.
    return Path(str(ref))


def seed_builtins(target_rules_dir: Path, *, force: bool = False) -> list[str]:
    """Copy bundled builtins into a target ``.vaultspec/rules/`` directory.

    Only copies files that don't already exist unless *force* is True.

    Args:
        target_rules_dir: The ``.vaultspec/rules/`` directory to populate.
        force: Overwrite existing files.

    Returns:
        List of relative paths (forward-slash separated) that were written.
    """
    src = _builtins_root()
    written: list[str] = []

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
        dest = target_rules_dir / rel

        if dest.exists() and not force:
            continue

        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_file, dest)
        written.append(str(rel).replace("\\", "/"))

    return written


def list_builtins() -> list[str]:
    """Return relative paths of all bundled builtin files.

    Returns:
        Sorted list of relative paths (forward-slash separated).
    """
    src = _builtins_root()
    paths: list[str] = []
    for f in sorted(src.rglob("*")):
        if not f.is_file():
            continue
        if f.name in ("__init__.py", "__pycache__") or "__pycache__" in str(f):
            continue
        paths.append(str(f.relative_to(src)).replace("\\", "/"))
    return paths

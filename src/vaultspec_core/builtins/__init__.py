"""Bundled builtin resources deployed during ``vaultspec-core install``.

Contains canonical rules, skills, agents, system prompts, templates, and hooks
seeded into ``.vaultspec/rules/`` on first install. Consumed by
:mod:`vaultspec_core.cli.root` via :func:`seed_builtins` and :func:`list_builtins`.
Uses :mod:`importlib.resources` for package-relative file access.
"""

from __future__ import annotations

import logging
import shutil
from importlib import resources
from pathlib import Path

logger = logging.getLogger(__name__)


def _builtins_root() -> Path:
    """Return the filesystem path to the bundled builtins directory.

    For installed (wheel) builds the content lives alongside this module.
    For editable / development installs the content is not copied into
    ``src/``; instead we resolve the canonical ``.vaultspec/rules/``
    directory at the repository root.
    """
    pkg_dir = Path(str(resources.files(__package__)))

    # Quick probe: a wheel build will contain at least the 'templates' dir.
    if (pkg_dir / "templates").is_dir():
        return pkg_dir

    # Editable install -- walk up to the repo root and use the canonical
    # source directly.  The repo root is identified by pyproject.toml.
    candidate = pkg_dir
    for _ in range(10):
        candidate = candidate.parent
        if (candidate / "pyproject.toml").is_file():
            rules = candidate / ".vaultspec" / "rules"
            if rules.is_dir():
                return rules
            break

    # Fallback: return the package directory regardless.
    return pkg_dir


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

        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dest)
        except OSError as exc:
            logger.warning("Failed to seed %s: %s", rel, exc)
            continue
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

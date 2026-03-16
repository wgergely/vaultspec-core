"""Track installed providers via a JSON manifest at ``.vaultspec/providers.json``.

The manifest enables shared directory protection during uninstall: when
multiple providers reference the same directory (e.g. ``.agents/skills/``),
uninstalling one provider must not remove directories still needed by others.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from .enums import Tool

logger = logging.getLogger(__name__)

MANIFEST_VERSION = "1.0"
MANIFEST_FILENAME = "providers.json"


def _manifest_path(target: Path) -> Path:
    return target / ".vaultspec" / MANIFEST_FILENAME


def read_manifest(target: Path) -> set[str]:
    """Read the set of installed provider names from the manifest.

    Returns an empty set if the manifest does not exist or is malformed.
    """
    path = _manifest_path(target)
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return set(data.get("installed", []))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to read provider manifest: %s", e)
        return set()


def write_manifest(target: Path, providers: set[str]) -> None:
    """Write the provider manifest with the given set of provider names."""
    path = _manifest_path(target)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "version": MANIFEST_VERSION,
        "installed": sorted(providers),
    }
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def add_providers(target: Path, names: list[str]) -> set[str]:
    """Add providers to the manifest and return the updated set."""
    current = read_manifest(target)
    current.update(names)
    write_manifest(target, current)
    return current


def remove_provider(target: Path, name: str) -> set[str]:
    """Remove a provider from the manifest and return the remaining set."""
    current = read_manifest(target)
    current.discard(name)
    write_manifest(target, current)
    return current


def providers_sharing_dir(
    target: Path, directory: Path, exclude: str | None = None
) -> set[str]:
    """Return installed providers that reference the given directory.

    Checks each installed provider's ``ToolConfig`` to see if any of its
    configured directories overlap with *directory*.  The *exclude*
    provider (typically the one being uninstalled) is omitted from the
    result.
    """
    from . import types as _t

    installed = read_manifest(target)
    if exclude:
        installed.discard(exclude)

    sharing: set[str] = set()
    for tool in Tool:
        if tool.value not in installed:
            continue
        cfg = _t.TOOL_CONFIGS.get(tool)
        if cfg is None:
            continue
        for d in (cfg.rules_dir, cfg.skills_dir, cfg.agents_dir):
            if d is not None and (d == directory or _is_parent(directory, d)):
                sharing.add(tool.value)
                break
    return sharing


def _is_parent(parent: Path, child: Path) -> bool:
    """Return True if *parent* is a parent directory of *child*."""
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False

"""Track installed providers via a JSON manifest at ``.vaultspec/providers.json``.

The manifest enables shared directory protection during uninstall: when
multiple providers reference the same directory (e.g. ``.agents/skills/``),
uninstalling one provider must not remove directories still needed by others.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .enums import Tool

logger = logging.getLogger(__name__)

MANIFEST_VERSION = "1.0"
MANIFEST_FILENAME = "providers.json"


def _manifest_path(target: Path) -> Path:
    return target / ".vaultspec" / MANIFEST_FILENAME


def read_manifest(target: Path) -> set[str]:
    """Read installed provider names from ``.vaultspec/providers.json``.

    Args:
        target: Workspace root directory.

    Returns:
        Set of installed provider name strings (e.g. ``{"claude", "gemini"}``),
        or an empty set if the manifest is absent or malformed.
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
    """Persist *providers* to ``.vaultspec/providers.json``.

    Args:
        target: Workspace root directory.
        providers: Set of provider name strings to record as installed.
    """
    path = _manifest_path(target)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "version": MANIFEST_VERSION,
        "installed": sorted(providers),
    }
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def add_providers(target: Path, names: list[str]) -> set[str]:
    """Add *names* to the manifest and return the updated provider set.

    Args:
        target: Workspace root directory.
        names: Provider names to add (e.g. ``["claude", "gemini"]``).

    Returns:
        Updated set of all installed provider names.
    """
    current = read_manifest(target)
    current.update(names)
    write_manifest(target, current)
    return current


def remove_provider(target: Path, name: str) -> set[str]:
    """Remove *name* from the manifest and return the remaining provider set.

    Args:
        target: Workspace root directory.
        name: Provider name to remove.

    Returns:
        Updated set of remaining installed provider names.
    """
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
        cfg = _t.get_context().tool_configs.get(tool)
        if cfg is None:
            continue
        for d in (cfg.rules_dir, cfg.skills_dir, cfg.agents_dir):
            if d is not None and (d == directory or _is_parent(directory, d)):
                sharing.add(tool.value)
                break
    return sharing


def installed_tool_configs() -> dict[Tool, Any]:
    """Return TOOL_CONFIGS filtered to only installed providers.

    Returns an empty dict when no manifest exists (framework not installed).
    """
    from . import types as _t

    ctx = _t.get_context()
    installed = read_manifest(ctx.target_dir)
    if not installed:
        return {}
    return {k: v for k, v in ctx.tool_configs.items() if v.name in installed}


def _is_parent(parent: Path, child: Path) -> bool:
    """Return True if *parent* is a parent directory of *child*."""
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False

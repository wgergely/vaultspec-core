"""Track installed providers via a JSON manifest at ``.vaultspec/providers.json``.

The manifest enables shared directory protection during uninstall: when
multiple providers reference the same directory (e.g. ``.agents/skills/``),
uninstalling one provider must not remove directories still needed by others.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .enums import Tool
from .helpers import atomic_write

logger = logging.getLogger(__name__)

MANIFEST_VERSION = "2.0"
MANIFEST_FILENAME = "providers.json"


@dataclass
class ManifestData:
    """Structured representation of the v2.0 provider manifest.

    Attributes:
        version: Manifest schema version string.
        vaultspec_version: Version of vaultspec-core that last wrote the manifest.
        installed_at: ISO-8601 timestamp of the initial install.
        serial: Monotonically increasing write counter.
        installed: Set of installed provider name strings.
        provider_state: Per-provider opaque state
            (e.g. ``{"claude": {"synced": "true"}}``).
        gitignore_managed: Whether vaultspec manages ``.gitignore``
            entries.
    """

    version: str = "2.0"
    vaultspec_version: str = ""
    installed_at: str = ""
    serial: int = 0
    installed: set[str] = field(default_factory=set)
    provider_state: dict[str, dict[str, str]] = field(default_factory=dict)
    gitignore_managed: bool = False


def _manifest_path(target: Path) -> Path:
    return target / ".vaultspec" / MANIFEST_FILENAME


def read_manifest_data(target: Path) -> ManifestData:
    """Read the full :class:`ManifestData` from ``.vaultspec/providers.json``.

    Handles v1.0 manifests transparently by using zero-values for fields
    introduced in v2.0.  Never raises on missing or malformed files - returns
    a default :class:`ManifestData` with an empty ``installed`` set instead.

    Args:
        target: Workspace root directory.

    Returns:
        Populated :class:`ManifestData` instance.
    """
    path = _manifest_path(target)
    if not path.exists():
        return ManifestData()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to read provider manifest: %s", e)
        return ManifestData()

    return ManifestData(
        version=raw.get("version", "1.0"),
        vaultspec_version=raw.get("vaultspec_version", ""),
        installed_at=raw.get("installed_at", ""),
        serial=int(raw.get("serial", 0)),
        installed=set(raw.get("installed", [])),
        provider_state=raw.get("provider_state", {}),
        gitignore_managed=bool(raw.get("gitignore_managed", False)),
    )


def write_manifest_data(target: Path, data: ManifestData) -> None:
    """Serialize *data* to ``.vaultspec/providers.json``.

    Auto-increments :attr:`ManifestData.serial` and forces
    :attr:`ManifestData.version` to the current :data:`MANIFEST_VERSION`
    before writing.

    Args:
        target: Workspace root directory.
        data: :class:`ManifestData` instance to persist.
    """
    serial = data.serial + 1

    path = _manifest_path(target)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": MANIFEST_VERSION,
        "vaultspec_version": data.vaultspec_version,
        "installed_at": data.installed_at,
        "serial": serial,
        "installed": sorted(data.installed),
        "provider_state": data.provider_state,
        "gitignore_managed": data.gitignore_managed,
    }
    atomic_write(path, json.dumps(payload, indent=2) + "\n")


def read_manifest(target: Path) -> set[str]:
    """Read installed provider names from ``.vaultspec/providers.json``.

    Backward-compatible convenience wrapper around :func:`read_manifest_data`.

    Args:
        target: Workspace root directory.

    Returns:
        Set of installed provider name strings (e.g. ``{"claude", "gemini"}``),
        or an empty set if the manifest is absent or malformed.
    """
    return read_manifest_data(target).installed


def write_manifest(target: Path, providers: set[str]) -> None:
    """Persist *providers* to ``.vaultspec/providers.json``.

    Backward-compatible convenience wrapper around :func:`write_manifest_data`.
    Reads the existing manifest first so that v2.0 metadata fields (timestamps,
    serial, provider state) are preserved across writes.

    Args:
        target: Workspace root directory.
        providers: Set of provider name strings to record as installed.
    """
    data = read_manifest_data(target)
    data.installed = set(providers)
    write_manifest_data(target, data)


def add_providers(target: Path, names: list[str]) -> set[str]:
    """Add *names* to the manifest and return the updated provider set.

    Uses :func:`read_manifest_data` / :func:`write_manifest_data` internally
    so that v2.0 metadata fields are preserved across read-modify-write cycles.

    Args:
        target: Workspace root directory.
        names: Provider names to add (e.g. ``["claude", "gemini"]``).

    Returns:
        Updated set of all installed provider names.
    """
    data = read_manifest_data(target)
    data.installed.update(names)
    write_manifest_data(target, data)
    return data.installed


def remove_provider(target: Path, name: str) -> set[str]:
    """Remove *name* from the manifest and return the remaining provider set.

    Uses :func:`read_manifest_data` / :func:`write_manifest_data` internally
    so that v2.0 metadata fields are preserved across read-modify-write cycles.

    Args:
        target: Workspace root directory.
        name: Provider name to remove.

    Returns:
        Updated set of remaining installed provider names.
    """
    data = read_manifest_data(target)
    data.installed.discard(name)
    data.provider_state.pop(name, None)
    write_manifest_data(target, data)
    return data.installed


def providers_sharing_file(
    target: Path, filepath: Path, exclude: str | None = None
) -> set[str]:
    """Return installed providers whose config files overlap with *filepath*.

    Checks each installed provider's ``ToolConfig`` to see if any of its
    config files match *filepath*.  The *exclude* provider (typically the
    one being uninstalled) is omitted from the result.
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
        for f in (cfg.config_file, cfg.rule_ref_config_file, cfg.native_config_file):
            if f is not None and f == filepath:
                sharing.add(tool.value)
                break
    return sharing


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

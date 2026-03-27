"""Signal collectors for workspace and provider diagnosis.

Each collector examines a single diagnostic axis and returns the appropriate
:mod:`~vaultspec_core.core.diagnosis.signals` enum value.  All imports from
``core.*`` modules are deferred inside function bodies to prevent import cycles.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from .signals import (
    BuiltinVersionSignal,
    ConfigSignal,
    ContentSignal,
    FrameworkSignal,
    GitignoreSignal,
    ManifestEntrySignal,
    ProviderDirSignal,
)

logger = logging.getLogger(__name__)

# Tool -> primary directory name mapping.  Kept here rather than imported from
# enums to avoid pulling the full enum module at import time; the mapping is
# stable and mirrors :class:`~vaultspec_core.core.enums.DirName`.
_TOOL_DIR: dict[str, str] = {
    "claude": ".claude",
    "gemini": ".gemini",
    "antigravity": ".agents",
    "codex": ".codex",
}


def collect_framework_presence(target: Path) -> FrameworkSignal:
    """Check whether the vaultspec framework directory is present and valid.

    Args:
        target: Workspace root directory.

    Returns:
        :class:`~vaultspec_core.core.diagnosis.signals.FrameworkSignal`
        reflecting the observed state.
    """
    fw_dir = target / ".vaultspec"
    if not fw_dir.exists():
        return FrameworkSignal.MISSING

    manifest_path = fw_dir / "providers.json"
    if not manifest_path.exists():
        return FrameworkSignal.CORRUPTED

    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return FrameworkSignal.CORRUPTED

    if "installed" not in raw:
        return FrameworkSignal.CORRUPTED

    return FrameworkSignal.PRESENT


def collect_manifest_coherence(target: Path) -> dict[str, ManifestEntrySignal]:
    """Compare the manifest's installed set against provider directories on disk.

    Args:
        target: Workspace root directory.

    Returns:
        Mapping of :class:`~vaultspec_core.core.enums.Tool` value strings to
        :class:`~vaultspec_core.core.diagnosis.signals.ManifestEntrySignal`.
    """
    from ..enums import Tool
    from ..manifest import read_manifest_data

    manifest = read_manifest_data(target)
    result: dict[str, ManifestEntrySignal] = {}

    for tool in Tool:
        dir_name = _TOOL_DIR.get(tool.value)
        if dir_name is None:
            continue

        in_manifest = tool.value in manifest.installed
        dir_exists = (target / dir_name).is_dir()

        if in_manifest and dir_exists:
            result[tool.value] = ManifestEntrySignal.COHERENT
        elif in_manifest and not dir_exists:
            result[tool.value] = ManifestEntrySignal.ORPHANED
        elif not in_manifest and dir_exists:
            result[tool.value] = ManifestEntrySignal.UNTRACKED
        else:
            result[tool.value] = ManifestEntrySignal.NOT_INSTALLED

    return result


def collect_provider_dir_state(target: Path, tool_value: str) -> ProviderDirSignal:
    """Assess the completeness of a provider's configuration directory.

    Args:
        target: Workspace root directory.
        tool_value: The :class:`~vaultspec_core.core.enums.Tool` ``.value``
            string (e.g. ``"claude"``).

    Returns:
        :class:`~vaultspec_core.core.diagnosis.signals.ProviderDirSignal`
        reflecting the observed state.
    """
    from ..enums import Tool
    from ..types import get_context

    dir_name = _TOOL_DIR.get(tool_value)
    if dir_name is None:
        return ProviderDirSignal.MISSING

    provider_dir = target / dir_name
    if not provider_dir.exists():
        return ProviderDirSignal.MISSING

    # Check if directory is empty
    try:
        children = list(provider_dir.iterdir())
    except OSError:
        return ProviderDirSignal.MISSING

    if not children:
        return ProviderDirSignal.EMPTY

    # Resolve expected subdirectories from ToolConfig
    tool = Tool(tool_value)
    try:
        ctx = get_context()
        cfg = ctx.tool_configs.get(tool)
    except LookupError:
        cfg = None

    if cfg is None:
        # Without config we cannot assess completeness beyond non-empty
        return ProviderDirSignal.PARTIAL

    expected_dirs: list[Path] = []
    for d in (cfg.rules_dir, cfg.skills_dir, cfg.agents_dir):
        if d is not None:
            expected_dirs.append(d)

    if not expected_dirs:
        # No subdirectories expected - non-empty is complete enough
        return ProviderDirSignal.COMPLETE

    all_present = True
    for d in expected_dirs:
        if not d.is_dir():
            all_present = False
            continue
        md_files = list(d.glob("*.md"))
        if not md_files:
            all_present = False

    if all_present:
        return ProviderDirSignal.COMPLETE

    return ProviderDirSignal.PARTIAL


def collect_builtin_version_state(target: Path) -> BuiltinVersionSignal:
    """Check whether built-in resource snapshots are current.

    Args:
        target: Workspace root directory.

    Returns:
        :class:`~vaultspec_core.core.diagnosis.signals.BuiltinVersionSignal`
        reflecting the observed state.
    """
    from ..revert import list_modified_builtins

    vaultspec_dir = target / ".vaultspec"
    snapshots_dir = vaultspec_dir / "_snapshots"

    results = list_modified_builtins(vaultspec_dir)

    if not results and not snapshots_dir.exists():
        return BuiltinVersionSignal.NO_SNAPSHOTS

    for entry in results:
        if entry["status"] == "missing":
            return BuiltinVersionSignal.DELETED

    for entry in results:
        if entry["status"] == "modified":
            return BuiltinVersionSignal.MODIFIED

    return BuiltinVersionSignal.CURRENT


def collect_config_state(target: Path, tool_value: str) -> ConfigSignal:
    """Assess the state of a provider's root configuration file.

    Args:
        target: Workspace root directory.
        tool_value: The :class:`~vaultspec_core.core.enums.Tool` ``.value``
            string (e.g. ``"claude"``).

    Returns:
        :class:`~vaultspec_core.core.diagnosis.signals.ConfigSignal`
        reflecting the observed state.
    """
    from ..enums import Tool
    from ..types import get_context

    tool = Tool(tool_value)

    try:
        ctx = get_context()
        cfg = ctx.tool_configs.get(tool)
    except LookupError:
        return ConfigSignal.MISSING

    if cfg is None:
        return ConfigSignal.MISSING

    config_file = cfg.config_file
    if config_file is None:
        return ConfigSignal.MISSING

    if not config_file.exists():
        return ConfigSignal.MISSING

    try:
        content = config_file.read_text(encoding="utf-8")
    except OSError:
        return ConfigSignal.MISSING

    # Detect both legacy AUTO-GENERATED header and current <vaultspec> tags
    if "AUTO-GENERATED" in content or "<vaultspec " in content:
        return ConfigSignal.OK

    return ConfigSignal.FOREIGN


def collect_mcp_config_state(target: Path) -> ConfigSignal:
    """Assess the state of the ``.mcp.json`` MCP configuration.

    Args:
        target: Workspace root directory.

    Returns:
        :class:`~vaultspec_core.core.diagnosis.signals.ConfigSignal`
        reflecting the observed MCP configuration state.
    """
    mcp_path = target / ".mcp.json"
    if not mcp_path.exists():
        return ConfigSignal.PARTIAL_MCP

    try:
        raw = json.loads(mcp_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return ConfigSignal.PARTIAL_MCP

    if not isinstance(raw, dict):
        return ConfigSignal.PARTIAL_MCP

    servers = raw.get("mcpServers")
    if not isinstance(servers, dict):
        return ConfigSignal.PARTIAL_MCP

    if "vaultspec-core" not in servers:
        return ConfigSignal.PARTIAL_MCP

    if len(servers) > 1:
        return ConfigSignal.USER_MCP

    return ConfigSignal.OK


def collect_gitignore_state(target: Path) -> GitignoreSignal:
    """Assess the state of vaultspec-managed ``.gitignore`` entries.

    Args:
        target: Workspace root directory.

    Returns:
        :class:`~vaultspec_core.core.diagnosis.signals.GitignoreSignal`
        reflecting the observed state.
    """
    from ..gitignore import DEFAULT_ENTRIES, MARKER_BEGIN, MARKER_END

    gi_path = target / ".gitignore"
    if not gi_path.exists():
        return GitignoreSignal.NO_FILE

    try:
        content = gi_path.read_text(encoding="utf-8")
    except OSError:
        return GitignoreSignal.NO_FILE

    has_begin = MARKER_BEGIN in content
    has_end = MARKER_END in content

    if has_begin != has_end:
        return GitignoreSignal.CORRUPTED

    if not has_begin and not has_end:
        return GitignoreSignal.NO_ENTRIES

    # Both markers present - extract the block and compare entries
    lines = content.splitlines()
    begin_idx: int | None = None
    end_idx: int | None = None
    for i, line in enumerate(lines):
        stripped = line.rstrip()
        if stripped == MARKER_BEGIN:
            begin_idx = i
        elif stripped == MARKER_END:
            end_idx = i

    if begin_idx is None or end_idx is None or end_idx <= begin_idx:
        return GitignoreSignal.CORRUPTED

    block_entries = [
        line.rstrip() for line in lines[begin_idx + 1 : end_idx] if line.strip()
    ]

    if block_entries == DEFAULT_ENTRIES:
        return GitignoreSignal.COMPLETE

    return GitignoreSignal.PARTIAL


def collect_content_integrity(
    target: Path, tool_value: str
) -> dict[str, ContentSignal]:
    """Check content integrity of managed rule files for a provider.

    Simplified implementation that checks file existence only.  SHA-256
    content comparison is deferred to a later iteration.

    Args:
        target: Workspace root directory.
        tool_value: The :class:`~vaultspec_core.core.enums.Tool` ``.value``
            string (e.g. ``"claude"``).

    Returns:
        Mapping of filename to
        :class:`~vaultspec_core.core.diagnosis.signals.ContentSignal`.
    """
    from ..enums import Tool
    from ..types import get_context

    tool = Tool(tool_value)
    result: dict[str, ContentSignal] = {}

    try:
        ctx = get_context()
        cfg = ctx.tool_configs.get(tool)
    except LookupError:
        return result

    if cfg is None or cfg.rules_dir is None:
        return result

    dest_dir = cfg.rules_dir
    source_dir = ctx.rules_src_dir

    # Collect files from destination
    dest_files: set[str] = set()
    if dest_dir.is_dir():
        dest_files = {f.name for f in dest_dir.glob("*.md")}

    # Collect files from source
    source_files: set[str] = set()
    if source_dir.is_dir():
        source_files = {f.name for f in source_dir.glob("*.md")}

    # Files in both
    for name in dest_files & source_files:
        result[name] = ContentSignal.CLEAN

    # Files only in destination
    for name in dest_files - source_files:
        result[name] = ContentSignal.STALE

    # Files only in source
    for name in source_files - dest_files:
        result[name] = ContentSignal.MISSING

    return result

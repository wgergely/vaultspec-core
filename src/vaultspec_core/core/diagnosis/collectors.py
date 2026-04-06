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

_tool_dir_validated = False


def _validate_tool_dir() -> None:
    """Verify ``_TOOL_DIR`` covers every Tool member.

    Called once on first use to catch drift between the mapping and the enum.
    """
    global _tool_dir_validated
    if _tool_dir_validated:
        return

    from ..enums import Tool

    enum_values = {t.value for t in Tool}
    mapping_keys = set(_TOOL_DIR)
    if mapping_keys != enum_values:
        missing = enum_values - mapping_keys
        extra = mapping_keys - enum_values
        raise RuntimeError(
            f"_TOOL_DIR is out of sync with Tool enum: missing={missing} extra={extra}"
        )
    _tool_dir_validated = True


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
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Cannot read manifest %s: %s", manifest_path, exc)
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

    _validate_tool_dir()

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
    except OSError as exc:
        logger.warning("Cannot read provider directory %s: %s", provider_dir, exc)
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

    # Build a set of known paths to detect foreign content
    known_paths: set[Path] = set()
    for d in expected_dirs:
        known_paths.add(d)

    # Config files are also known content
    if cfg.config_file is not None:
        known_paths.add(cfg.config_file)
    if cfg.native_config_file is not None:
        known_paths.add(cfg.native_config_file)
    if cfg.system_file is not None:
        known_paths.add(cfg.system_file)

    all_present = True
    for d in expected_dirs:
        if not d.is_dir():
            all_present = False
            continue
        # Rules/agents dirs contain flat .md files; skills dirs contain
        # subdirectories each holding a SKILL.md.  Accept either layout.
        md_files = list(d.glob("*.md"))
        skill_files = list(d.glob("*/SKILL.md")) if not md_files else []
        if not md_files and not skill_files:
            all_present = False

    # Check for files in the provider directory that don't match known patterns
    has_foreign = False
    for child in children:
        child_resolved = child.resolve()
        # Known subdirectory
        if any(child_resolved == kp.resolve() for kp in known_paths if kp is not None):
            continue
        # Known config file at provider level
        if child.is_file() and any(
            child_resolved == kp.resolve() for kp in known_paths if kp is not None
        ):
            continue
        # Subdirectories of expected dirs are fine
        if child.is_dir() and any(child_resolved == d.resolve() for d in expected_dirs):
            continue
        # If we reach here, the child is not a known resource
        has_foreign = True
        break

    if has_foreign:
        return ProviderDirSignal.MIXED

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
    except OSError as exc:
        logger.warning("Cannot read config %s: %s", config_file, exc)
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
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Cannot read MCP config %s: %s", mcp_path, exc)
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
    from ..gitignore import _find_markers, get_recommended_entries

    gi_path = target / ".gitignore"
    if not gi_path.exists():
        return GitignoreSignal.NO_FILE

    try:
        content = gi_path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("Cannot read .gitignore %s: %s", gi_path, exc)
        return GitignoreSignal.NO_FILE

    lines = [line.strip() for line in content.splitlines()]
    begins, ends = _find_markers(lines)

    if not begins and not ends:
        return GitignoreSignal.NO_ENTRIES

    # Any state that isn't exactly one BEGIN before exactly one END is corrupted.
    if len(begins) != 1 or len(ends) != 1 or begins[0] >= ends[0]:
        return GitignoreSignal.CORRUPTED

    begin_idx = begins[0]
    end_idx = ends[0]
    block_entries = [
        line.rstrip() for line in lines[begin_idx + 1 : end_idx] if line.strip()
    ]

    # Contradictory check: is an entry in the block explicitly unignored elsewhere?
    # (i.e. starts with "!")
    unignored = {line[1:].strip() for line in lines if line.startswith("!")}
    for entry in block_entries:
        if entry in unignored or entry.rstrip("/") in unignored:
            return GitignoreSignal.CORRUPTED

    recommended = get_recommended_entries(target)

    # Check if all recommended entries are present in the block.
    # We allow extra entries (idempotency is handled by ensure_gitignore_block).
    if all(entry in block_entries for entry in recommended):
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
        if name.endswith("-system.builtin.md"):
            continue  # Synthesized by system_sync(), not sourced
        result[name] = ContentSignal.STALE

    # Files only in source
    for name in source_files - dest_files:
        result[name] = ContentSignal.MISSING

    return result

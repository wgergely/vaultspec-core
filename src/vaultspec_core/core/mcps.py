"""Manage MCP server definitions for the vaultspec framework.

This module handles MCP server definition collection, custom definition
scaffolding, and the merge pipeline that syncs definitions into ``.mcp.json``.
Unlike rules/skills/agents (which use Markdown sources and per-tool directory
sync), MCP definitions are JSON files merged into a single provider-agnostic
``.mcp.json`` file.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from . import types as _t
from .exceptions import ResourceExistsError, ResourceNotFoundError
from .helpers import atomic_write, ensure_dir
from .types import SyncResult

logger = logging.getLogger(__name__)


def _server_name(filename: str) -> str:
    """Derive the MCP server name from a definition filename.

    Strips ``.builtin.json`` as a unit first, then falls back to ``.json``.

    Args:
        filename: The definition filename (e.g. ``vaultspec-core.builtin.json``).

    Returns:
        The server name (e.g. ``vaultspec-core``).
    """
    if filename.endswith(".builtin.json"):
        return filename[: -len(".builtin.json")]
    if filename.endswith(".json"):
        return filename[: -len(".json")]
    return filename


def _get_mcps_src_dir() -> Path | None:
    """Return the MCP source directory from the active context, or ``None``."""
    try:
        return _t.get_context().mcps_src_dir
    except LookupError:
        return None


def collect_mcp_servers(
    warnings: list[str] | None = None,
) -> dict[str, tuple[Path, dict[str, Any]]]:
    """Collect MCP server definitions from ``.vaultspec/rules/mcps/``.

    Reads and parses every ``.json`` file in the MCP source directory,
    returning a mapping of server name to (source path, parsed config).

    Args:
        warnings: Optional list to append parse-error messages to.

    Returns:
        Mapping of server name to ``(source_path, config_dict)``.
    """
    mcps_dir = _get_mcps_src_dir()
    if mcps_dir is None or not mcps_dir.exists():
        return {}

    sources: dict[str, tuple[Path, dict[str, Any]]] = {}
    for f in sorted(mcps_dir.glob("*.json")):
        try:
            raw = json.loads(f.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                msg = f"MCP definition {f.name} is not a JSON object"
                logger.error(msg)
                if warnings is not None:
                    warnings.append(msg)
                continue
            name = _server_name(f.name)
            sources[name] = (f, raw)
        except (json.JSONDecodeError, OSError) as e:
            msg = f"Failed to read/parse MCP definition {f}: {e}"
            logger.error(msg)
            if warnings is not None:
                warnings.append(msg)
    return sources


def mcp_list() -> list[dict[str, str]]:
    """Return a list of MCP server metadata dicts.

    Each dict contains ``"name"`` and ``"source"`` (``"Built-in"`` or
    ``"Custom"``).
    """
    mcps_dir = _get_mcps_src_dir()
    if mcps_dir is None or not mcps_dir.exists():
        return []

    items: list[dict[str, str]] = []
    for f in sorted(mcps_dir.glob("*.json")):
        source = "Built-in" if f.name.endswith(".builtin.json") else "Custom"
        items.append({"name": _server_name(f.name), "source": source})
    return items


def mcp_add(
    name: str,
    config: dict[str, Any] | None = None,
    force: bool = False,
) -> Path:
    """Scaffold a new custom MCP server definition.

    Args:
        name: Server name.
        config: Server configuration dict.  Uses an empty scaffold when
            ``None``.
        force: Whether to overwrite an existing definition.

    Returns:
        Path to the created definition file.

    Raises:
        ResourceExistsError: If the definition exists and *force* is ``False``.
    """
    mcps_dir = _get_mcps_src_dir()
    if mcps_dir is None:
        raise ResourceNotFoundError(
            "MCP source directory not configured.",
            hint="Run 'vaultspec-core install' first.",
        )
    ensure_dir(mcps_dir)

    file_name = name if name.endswith(".json") else f"{name}.json"
    file_path = mcps_dir / file_name

    if file_path.exists() and not force:
        raise ResourceExistsError(
            f"MCP definition '{file_name}' exists. Use --force to overwrite."
        )

    server_config = config if config is not None else {"command": "", "args": []}
    atomic_write(file_path, json.dumps(server_config, indent=2) + "\n")
    logger.info("Created MCP definition: %s", file_path)
    return file_path


def mcp_remove(name: str) -> Path:
    """Delete an MCP server definition.

    Searches for both ``{name}.json`` and ``{name}.builtin.json``.

    Args:
        name: Server name.

    Returns:
        Path to the removed definition file.

    Raises:
        ResourceNotFoundError: If no definition file matches *name*.
    """
    mcps_dir = _get_mcps_src_dir()
    if mcps_dir is None or not mcps_dir.exists():
        raise ResourceNotFoundError(
            f"MCP definition '{name}' not found.",
            hint="No MCP definitions directory exists.",
        )

    for suffix in (".builtin.json", ".json"):
        candidate = mcps_dir / f"{name}{suffix}"
        if candidate.exists():
            candidate.unlink()
            logger.info("Removed MCP definition: %s", candidate)
            return candidate

    raise ResourceNotFoundError(f"MCP definition '{name}' not found.")


def mcp_sync(
    dry_run: bool = False,
    force: bool = False,
) -> SyncResult:
    """Sync MCP server definitions into ``.mcp.json``.

    Collects all definitions from the MCP source directory, merges them
    into the workspace ``.mcp.json`` file.  User-added entries (not
    matching any definition file) are always preserved.

    Args:
        dry_run: If ``True``, compute changes without writing.
        force: Overwrite entries that differ from their definitions.

    Returns:
        :class:`~vaultspec_core.core.types.SyncResult` with sync statistics.
    """
    result = SyncResult()
    parse_warnings: list[str] = []
    sources = collect_mcp_servers(warnings=parse_warnings)
    result.warnings.extend(parse_warnings)

    try:
        target_dir = _t.get_context().target_dir
    except LookupError:
        result.errors.append("No workspace context available for MCP sync.")
        return result

    mcp_json = target_dir / ".mcp.json"

    # Read existing config
    existing: dict[str, Any] = {}
    if mcp_json.exists():
        try:
            raw = json.loads(mcp_json.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                existing = raw
        except (json.JSONDecodeError, OSError) as exc:
            result.warnings.append(f"Cannot parse existing .mcp.json: {exc}")

    servers = existing.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        servers = {}
        existing["mcpServers"] = servers

    changed = False
    for name, (_path, config) in sources.items():
        if name not in servers:
            servers[name] = config
            result.added += 1
            result.items.append((name, "added"))
            changed = True
        elif servers[name] == config:
            result.skipped += 1
        else:
            if force:
                servers[name] = config
                result.updated += 1
                result.items.append((name, "updated"))
                changed = True
            else:
                result.skipped += 1
                result.warnings.append(
                    f"MCP server '{name}' differs from definition "
                    f"(use --force to overwrite)"
                )

    if changed and not dry_run:
        atomic_write(mcp_json, json.dumps(existing, indent=2) + "\n")

    return result


def mcp_uninstall(target_dir: Path, *, dry_run: bool = False) -> list[str]:
    """Remove all registry-managed MCP entries from ``.mcp.json``.

    Collects managed server names from the registry source directory and
    removes each from ``.mcp.json``.  User-added entries are preserved.
    If no servers remain, the file is deleted.

    Args:
        target_dir: Workspace root directory.
        dry_run: When ``True``, returns names without modifying files.

    Returns:
        List of server names that were (or would be) removed.
    """
    sources = collect_mcp_servers()
    managed_names = set(sources.keys())

    # If no registry is available, fall back to removing known built-in names
    if not managed_names:
        managed_names = {"vaultspec-core"}

    mcp_json = target_dir / ".mcp.json"
    if not mcp_json.exists():
        return []

    try:
        raw = json.loads(mcp_json.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []

    if not isinstance(raw, dict):
        return []

    servers = raw.get("mcpServers", {})
    if not isinstance(servers, dict):
        return []

    removed: list[str] = []
    for name in managed_names:
        if name in servers:
            removed.append(name)
            if not dry_run:
                del servers[name]

    if not dry_run and removed:
        if servers:
            atomic_write(mcp_json, json.dumps(raw, indent=2) + "\n")
        else:
            mcp_json.unlink()

    return removed

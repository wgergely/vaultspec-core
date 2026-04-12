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
from .exceptions import ResourceExistsError, ResourceNotFoundError, VaultSpecError
from .helpers import advisory_lock, atomic_write, ensure_dir
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


def _validate_server_name(name: str) -> None:
    """Raise :class:`VaultSpecError` if *name* is unsafe for use as a filename.

    Guards against path traversal, empty names, reserved suffixes, and
    OS-unsafe characters.
    """
    if not name or not name.strip():
        raise VaultSpecError("MCP server name must not be empty.")
    if "/" in name or "\\" in name or ".." in name:
        raise VaultSpecError(f"Invalid MCP server name: {name}")
    if name.endswith(".builtin.json") or name.endswith(".builtin"):
        raise VaultSpecError(
            "Cannot use '.builtin' suffix (reserved for package-bundled definitions)."
        )


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
            if not name:
                continue
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

    items: dict[str, dict[str, str]] = {}
    for f in sorted(mcps_dir.glob("*.json")):
        name = _server_name(f.name)
        if not name:
            continue
        is_builtin = f.name.endswith(".builtin.json")
        if name in items:
            if not is_builtin:
                items[name]["source"] = "Custom (shadows Built-in)"
        else:
            items[name] = {
                "name": name,
                "source": "Built-in" if is_builtin else "Custom",
            }
    return list(items.values())


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

    _validate_server_name(name)

    if config is not None and not isinstance(config, dict):
        raise VaultSpecError("MCP configuration must be a JSON object (dict).")

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

    Searches for ``{name}.json`` first (custom), then ``{name}.builtin.json``.
    This prioritizes removing custom overrides so users can revert to the
    built-in definition.

    Args:
        name: Server name.

    Returns:
        Path to the removed definition file.

    Raises:
        ResourceNotFoundError: If no definition file matches *name*.
    """
    _validate_server_name(name)

    mcps_dir = _get_mcps_src_dir()
    if mcps_dir is None or not mcps_dir.exists():
        raise ResourceNotFoundError(
            f"MCP definition '{name}' not found.",
            hint="No MCP definitions directory exists.",
        )

    for suffix in (".json", ".builtin.json"):
        candidate = mcps_dir / f"{name}{suffix}"
        if candidate.exists():
            candidate.unlink()
            logger.info("Removed MCP definition: %s", candidate)
            return candidate

    raise ResourceNotFoundError(f"MCP definition '{name}' not found.")


_MANAGED_KEY = "_vaultspecManaged"


def mcp_sync(
    dry_run: bool = False,
    force: bool = False,
    prune: bool = False,
) -> SyncResult:
    """Sync MCP server definitions into ``.mcp.json``.

    Collects all definitions from the MCP source directory, merges them
    into the workspace ``.mcp.json`` file, and (when ``prune`` is set)
    removes managed entries whose source files have been deleted.

    Ownership tracking is persisted in ``.mcp.json`` itself under the
    reserved top-level key ``_vaultspecManaged`` (a sorted list of
    server names that vaultspec created via this function). Entries
    that pre-existed without being added by ``mcp_sync`` never enter
    the managed set, so user-added servers are always preserved —
    even if they happen to share a name with a current source. This
    mirrors the content-marker ownership pattern used by
    ``sync_files`` for rule/agent/skill files.

    Args:
        dry_run: If ``True``, compute changes without writing.
        force: Overwrite entries that differ from their definitions.
        prune: If ``True``, remove managed entries whose source files
            have been deleted. Mirrors the ``prune`` behavior of
            ``rules_sync``/``agents_sync``/``skills_sync``.

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

    with advisory_lock(mcp_json):
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

        if _MANAGED_KEY in existing:
            raw_managed = existing.get(_MANAGED_KEY, [])
            if isinstance(raw_managed, list):
                managed: set[str] = {str(n) for n in raw_managed if isinstance(n, str)}
            else:
                managed = set()
        else:
            # Legacy migration: workspaces created before ownership
            # tracking shipped have no sidecar key. Treat any
            # pre-existing entry whose name matches a current source
            # as managed — this preserves the legacy "differs, use
            # --force" warning behaviour for already-installed
            # entries. After this sync the sidecar is written and
            # future syncs use strict ownership.
            managed = set(servers.keys()) & set(sources.keys())

        changed = False
        for name, (_path, config) in sources.items():
            if name not in servers:
                # New entry — vaultspec creates it and takes ownership.
                servers[name] = config
                managed.add(name)
                result.added += 1
                result.items.append((name, "added"))
                changed = True
            elif name in managed:
                # Previously managed by vaultspec — sync content.
                if servers[name] == config:
                    result.skipped += 1
                elif force:
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
            else:
                # User-added entry that shares a name with a current
                # source. Preserve it; never take ownership implicitly.
                result.skipped += 1
                result.warnings.append(
                    f"MCP server '{name}' is user-managed and shares "
                    f"its name with a vaultspec source; skipping. "
                    f"Rename one to resolve."
                )

        source_names = set(sources.keys())
        if prune:
            for name in sorted(managed - source_names):
                if name in servers:
                    servers.pop(name)
                    result.pruned += 1
                    result.items.append((name, "[DELETE]"))
                    changed = True
                managed.discard(name)

        # Reconcile managed set with what is actually in ``servers``
        # (defensive cleanup against external mutations).
        managed &= set(servers.keys())

        # Persist managed set; remove the key entirely when empty so
        # we never write a dangling sidecar.
        prior_managed = existing.get(_MANAGED_KEY)
        new_managed_value = sorted(managed) if managed else None
        if new_managed_value is None:
            if _MANAGED_KEY in existing:
                del existing[_MANAGED_KEY]
                changed = True
        else:
            if prior_managed != new_managed_value:
                existing[_MANAGED_KEY] = new_managed_value
                changed = True

        if changed and not dry_run:
            # If pruning emptied the file entirely, remove it instead
            # of leaving an orphan ``{"mcpServers": {}}`` artefact.
            if not servers and _MANAGED_KEY not in existing:
                if mcp_json.exists():
                    mcp_json.unlink()
            else:
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

    with advisory_lock(mcp_json):
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

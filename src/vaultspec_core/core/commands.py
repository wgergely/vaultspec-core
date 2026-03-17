"""Implement the top-level operational commands mounted into the root CLI.

This module contains the business logic behind workspace initialization,
install, uninstall, and sync. It sits above the lower-level resource-management
modules and provides the user-facing command behaviors that do not belong
to a dedicated nested Typer namespace.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from . import types as _t
from .enums import ProviderCapability, Tool
from .exceptions import (
    ProviderError,
    ProviderNotInstalledError,
    WorkspaceNotInitializedError,
)
from .helpers import ensure_dir

logger = logging.getLogger(__name__)

# Valid provider arguments for install/uninstall commands.
VALID_PROVIDERS = {"all", "core", "claude", "gemini", "antigravity", "codex"}

# Map provider argument names to Tool enum members.
_PROVIDER_TO_TOOLS: dict[str, list[Tool]] = {
    "claude": [Tool.CLAUDE],
    "gemini": [Tool.GEMINI],
    "antigravity": [Tool.ANTIGRAVITY],
    "codex": [Tool.CODEX],
    "all": [Tool.CLAUDE, Tool.GEMINI, Tool.ANTIGRAVITY, Tool.CODEX],
    "core": [],
}


def _rel(target: Path, p: Path) -> str:
    return str(p.relative_to(target)).replace("\\", "/")


def _scaffold_core(target: Path, *, dry_run: bool = False) -> list[tuple[str, str]]:
    """Scaffold the .vaultspec/ and .vault/ directory structures.

    Returns a list of ``(relative_path, label)`` tuples.
    When *dry_run* is True, returns the manifest without writing anything.
    """
    fw_dir = target / ".vaultspec"
    vault_dir = target / ".vault"
    created: list[tuple[str, str]] = []

    for subdir in [
        "rules/rules",
        "rules/skills",
        "rules/agents",
        "rules/templates",
        "rules/system",
    ]:
        d = fw_dir / subdir
        if not dry_run:
            ensure_dir(d)
        created.append((_rel(target, d), "core (.vaultspec)"))

    for subdir in ["adr", "audit", "exec", "plan", "reference", "research"]:
        d = vault_dir / subdir
        if not dry_run:
            ensure_dir(d)
        created.append((_rel(target, d), "vault (.vault)"))

    return created


def _scaffold_provider(
    target: Path, tool: Tool, *, dry_run: bool = False
) -> list[tuple[str, str]]:
    """Scaffold directories for a single provider based on its ToolConfig.

    Returns a list of ``(relative_path, label)`` tuples.
    When *dry_run* is True, returns the manifest without writing anything.
    """
    cfg = _t.TOOL_CONFIGS.get(tool)
    if cfg is None:
        return []

    created: list[tuple[str, str]] = []
    caps = cfg.capabilities
    label = tool.value
    seen_rels: set[str] = set()

    def _add(rel: str, sublabel: str) -> None:
        if rel not in seen_rels:
            seen_rels.add(rel)
            created.append((rel, f"{label} ({sublabel})"))

    if ProviderCapability.RULES in caps and cfg.rules_dir:
        if not dry_run:
            ensure_dir(cfg.rules_dir)
        _add(_rel(target, cfg.rules_dir), "rules")

    if ProviderCapability.SKILLS in caps and cfg.skills_dir:
        if not dry_run:
            ensure_dir(cfg.skills_dir)
        _add(_rel(target, cfg.skills_dir), "skills")

    if ProviderCapability.AGENTS in caps and cfg.agents_dir:
        if not dry_run:
            ensure_dir(cfg.agents_dir)
        _add(_rel(target, cfg.agents_dir), "agents")

    if ProviderCapability.WORKFLOWS in caps:
        wf_dir = target / ".agents" / "workflows"
        if not dry_run:
            ensure_dir(wf_dir)
        _add(_rel(target, wf_dir), "workflows")

    if cfg.config_file:
        _add(_rel(target, cfg.config_file), "config")

    if cfg.rule_ref_config_file:
        _add(_rel(target, cfg.rule_ref_config_file), "config")

    if cfg.native_config_file:
        if not dry_run:
            ensure_dir(cfg.native_config_file.parent)
            if not cfg.native_config_file.exists():
                cfg.native_config_file.write_text("", encoding="utf-8")
        _add(_rel(target, cfg.native_config_file), "config")

    return created


def _scaffold_mcp_json(target: Path, *, dry_run: bool = False) -> list[tuple[str, str]]:
    """Scaffold .mcp.json for MCP server integration."""
    import json

    mcp_json = target / ".mcp.json"
    if mcp_json.exists():
        return []

    if not dry_run:
        mcp_config = {
            "mcpServers": {
                "vaultspec-core": {
                    "command": "uv",
                    "args": ["run", "vaultspec-mcp"],
                    "env": {"VAULTSPEC_TARGET_DIR": "."},
                }
            }
        }
        mcp_json.write_text(json.dumps(mcp_config, indent=2) + "\n", encoding="utf-8")
    return [(".mcp.json", "mcp")]


def _validate_provider(provider: str) -> None:
    """Validate that *provider* is a known provider name.

    Raises:
        ProviderError: If *provider* is not in :data:`VALID_PROVIDERS`.
    """
    if provider not in VALID_PROVIDERS:
        raise ProviderError(
            f"Unknown provider '{provider}'. "
            f"Valid: {', '.join(sorted(VALID_PROVIDERS))}"
        )


def init_run(force: bool = False, provider: str = "all") -> list[tuple[str, str]]:
    """Scaffold the .vaultspec/ and .vault/ directory structure.

    Returns:
        A deduplicated list of ``(relative_path, label)`` tuples for all
        created directories and files.
    """
    from vaultspec_core.config import get_config, reset_config
    from vaultspec_core.config.workspace import resolve_workspace
    from vaultspec_core.core.types import init_paths

    from .exceptions import ResourceExistsError

    cfg = get_config()
    fw_dir = _t.TARGET_DIR / cfg.framework_dir

    if fw_dir.exists() and not force:
        raise ResourceExistsError(f"{fw_dir} already exists. Use --force to overwrite.")

    created = _scaffold_core(_t.TARGET_DIR)

    # Seed builtin content into .vaultspec/rules/
    from vaultspec_core.builtins import seed_builtins

    rules_dir = fw_dir / "rules"
    seeded = seed_builtins(rules_dir, force=force)
    for rel in seeded:
        created.append((f".vaultspec/rules/{rel}", "builtin"))

    # Snapshot builtins for revert support
    from .revert import snapshot_builtins

    snapshot_builtins(fw_dir)

    # Re-resolve workspace after scaffolding
    reset_config()
    layout = resolve_workspace(target_override=_t.TARGET_DIR)
    init_paths(layout)

    # Scaffold provider directories
    tools = _PROVIDER_TO_TOOLS.get(provider, [])
    for tool in tools:
        created.extend(_scaffold_provider(_t.TARGET_DIR, tool))

    created.extend(_scaffold_mcp_json(_t.TARGET_DIR))

    # Write provider manifest
    from .manifest import add_providers

    provider_names = [t.value for t in tools]
    if provider_names:
        add_providers(_t.TARGET_DIR, provider_names)

    # Deduplicate by relative path, preserving order
    seen: dict[str, str] = {}
    for rel, label in created:
        seen.setdefault(rel, label)

    return list(seen.items())


def _ensure_tool_configs(path: Path) -> None:
    """Ensure TOOL_CONFIGS is populated, bootstrapping if needed.

    On a fresh project where ``.vaultspec/`` doesn't exist yet, temporarily
    creates the minimal structure so ``init_paths()`` can resolve the
    workspace layout and populate TOOL_CONFIGS.  All temporary artifacts
    (including the target directory itself if it was created) are cleaned up.
    """
    from vaultspec_core.config import reset_config
    from vaultspec_core.config.workspace import resolve_workspace
    from vaultspec_core.core.types import init_paths

    if _t.TOOL_CONFIGS:
        return

    fw_dir = path / ".vaultspec"
    temp_scaffold = not fw_dir.exists()
    # Track whether we created the target dir itself (for non-existent paths)
    created_target = not path.exists()

    if temp_scaffold:
        fw_dir.mkdir(parents=True, exist_ok=True)

    try:
        reset_config()
        layout = resolve_workspace(target_override=path)
        init_paths(layout)
    finally:
        if temp_scaffold:
            import shutil

            shutil.rmtree(fw_dir, ignore_errors=True)
            # If we created the target dir just for bootstrapping, remove it
            if created_target and path.exists():
                import contextlib

                with contextlib.suppress(OSError):
                    path.rmdir()  # only removes if empty


def install_run(
    path: Path,
    provider: str = "all",
    upgrade: bool = False,
    dry_run: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    """Deploy the vaultspec framework to a project directory.

    Args:
        path: Target directory.
        provider: Provider to install (``all``, ``core``, ``claude``, etc.).
        upgrade: Re-sync builtin rules without re-scaffolding.
        dry_run: Preview the manifest of files that would be created.
        force: Override contents if installation already exists.

    Returns:
        A dict describing the result:
        - ``"action"``: ``"dry_run"``, ``"upgrade"``, or ``"install"``
        - ``"items"``: list of ``(path, label)`` tuples (for dry_run)
        - ``"seeded_count"``: number of re-seeded files (for upgrade)

    Raises:
        ProviderError: If *provider* is invalid.
        ResourceExistsError: If already installed and *force*/*upgrade* not set.
    """
    from vaultspec_core.config import reset_config
    from vaultspec_core.config.workspace import WorkspaceError, resolve_workspace
    from vaultspec_core.core.types import init_paths

    from .exceptions import ResourceExistsError

    _validate_provider(provider)

    _t.TARGET_DIR = path

    if dry_run:
        _ensure_tool_configs(path)

        manifest = _scaffold_core(path, dry_run=True)

        # Include builtin files that would be seeded
        from vaultspec_core.builtins import list_builtins

        for builtin_rel in list_builtins():
            manifest.append((f".vaultspec/rules/{builtin_rel}", "builtin"))

        tools = _PROVIDER_TO_TOOLS.get(provider, [])
        for tool in tools:
            manifest.extend(_scaffold_provider(path, tool, dry_run=True))
        manifest.extend(_scaffold_mcp_json(path, dry_run=True))

        # Deduplicate preserving order (by relative path)
        seen: dict[str, str] = {}
        for rel, label in manifest:
            seen.setdefault(rel, label)

        return {"action": "dry_run", "items": list(seen.items()), "path": path}

    if upgrade:
        try:
            layout = resolve_workspace(target_override=path)
            init_paths(layout)
        except WorkspaceError as e:
            raise WorkspaceNotInitializedError(
                f"Cannot upgrade: {e}",
                hint=f"Run 'vaultspec-core install {path}' first.",
            ) from e

        # Re-seed builtins (force=True overwrites existing)
        from vaultspec_core.builtins import seed_builtins

        fw_dir = path / ".vaultspec"
        seeded = seed_builtins(fw_dir / "rules", force=True)

        # Re-snapshot builtins for revert support
        from .revert import snapshot_builtins

        snapshot_builtins(fw_dir)

        sync_target = provider if provider not in ("all", "core") else "all"
        sync_provider(sync_target, force=True)
        return {"action": "upgrade", "seeded_count": len(seeded), "path": path}

    fw_dir = path / ".vaultspec"
    if fw_dir.exists() and not force:
        raise ResourceExistsError(
            f"vaultspec is already installed at {path}. "
            "Use --upgrade to update, --force to override, or remove it "
            f"first with 'vaultspec-core uninstall {path}'."
        )

    created = init_run(force=force, provider=provider)

    reset_config()
    layout = resolve_workspace(target_override=path)
    init_paths(layout)

    sync_target = provider if provider not in ("all", "core") else "all"
    sync_provider(sync_target)
    return {"action": "install", "items": created, "path": path}


def _collect_provider_artifacts(
    path: Path, tool: Tool
) -> tuple[list[Path], list[Path]]:
    """Return (directories, files) managed by a single provider."""
    from .enums import DirName, FileName

    cfg = _t.TOOL_CONFIGS.get(tool)
    dirs: list[Path] = []
    files: list[Path] = []

    if tool == Tool.CLAUDE:
        dirs.append(path / DirName.CLAUDE.value)
        files.append(path / FileName.CLAUDE.value)
    elif tool == Tool.GEMINI:
        dirs.append(path / DirName.GEMINI.value)
        # Root GEMINI.md is shared with Antigravity — handled below
    elif tool == Tool.ANTIGRAVITY:
        dirs.append(path / DirName.ANTIGRAVITY.value)
        files.append(path / FileName.GEMINI.value)
    elif tool == Tool.CODEX:
        dirs.append(path / DirName.CODEX.value)
        files.append(path / FileName.AGENTS.value)

    if cfg and cfg.native_config_file and cfg.native_config_file.parent not in dirs:
        dirs.append(cfg.native_config_file.parent)

    return dirs, files


def uninstall_run(
    path: Path,
    provider: str = "all",
    keep_vault: bool = False,
    dry_run: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    """Remove the vaultspec framework from a project directory.

    Args:
        path: Target directory.
        provider: Provider to uninstall (``all``, ``core``, ``<provider>``).
        keep_vault: Preserve ``.vault/`` documentation directory.
        dry_run: Preview what would be removed without deleting.
        force: Required to execute. Uninstall is destructive.

    Returns:
        A dict describing the result:
        - ``"action"``: ``"dry_run"`` or ``"uninstall"``
        - ``"removed"``: list of ``(path, label)`` tuples

    Raises:
        ProviderError: If *provider* is invalid or *force* not set.
    """
    import shutil

    from .manifest import providers_sharing_dir, remove_provider

    # Safety gate: require --force for destructive operations
    if not force and not dry_run:
        raise ProviderError(
            "Uninstall is destructive. Pass --force to confirm, "
            "or use --dry-run to preview."
        )

    _t.TARGET_DIR = path
    _ensure_tool_configs(path)

    _validate_provider(provider)

    # Uninstalling "core" cascades to all providers
    effective_provider = "all" if provider == "core" else provider

    removed: list[tuple[str, str]] = []  # (path, label)

    # Label mapping for well-known directories and files
    dir_labels: dict[str, str] = {
        ".vaultspec": "core",
        ".vault": "vault",
        ".claude": "claude",
        ".gemini": "gemini",
        ".agents": "antigravity",
        ".codex": "codex",
    }
    file_labels: dict[str, str] = {
        "CLAUDE.md": "claude (config)",
        "GEMINI.md": "gemini (config)",
        "AGENTS.md": "codex (config)",
        ".mcp.json": "mcp",
    }

    if effective_provider == "all":
        # Remove everything
        managed_dirs = [
            path / ".vaultspec",
            path / ".claude",
            path / ".gemini",
            path / ".agents",
            path / ".codex",
        ]
        if not keep_vault:
            managed_dirs.append(path / ".vault")

        managed_files = [
            path / "CLAUDE.md",
            path / "GEMINI.md",
            path / "AGENTS.md",
            path / ".mcp.json",
        ]

        for d in managed_dirs:
            if d.exists():
                if not dry_run:
                    shutil.rmtree(d)
                label = dir_labels.get(d.name, "")
                removed.append((str(d).replace("\\", "/") + "/", label))

        for f in managed_files:
            if f.exists():
                if not dry_run:
                    f.unlink()
                label = file_labels.get(f.name, "")
                removed.append((str(f).replace("\\", "/"), label))

    else:
        # Per-provider uninstall with shared directory protection
        tools = _PROVIDER_TO_TOOLS.get(effective_provider, [])
        for tool in tools:
            dirs, files = _collect_provider_artifacts(path, tool)

            for d in dirs:
                if not d.exists():
                    continue
                # Check if another installed provider still needs this dir
                sharing = providers_sharing_dir(path, d, exclude=effective_provider)
                if sharing:
                    logger.info(
                        "Preserving %s (still used by: %s)",
                        d.relative_to(path),
                        ", ".join(sorted(sharing)),
                    )
                    continue

                if not dry_run:
                    shutil.rmtree(d)
                removed.append((str(d).replace("\\", "/") + "/", tool.value))

            for f in files:
                if not f.exists():
                    continue
                if not dry_run:
                    f.unlink()
                removed.append((str(f).replace("\\", "/"), f"{tool.value} (config)"))

        # Update manifest
        if not dry_run:
            for tool in tools:
                remove_provider(path, tool.value)

    action = "dry_run" if dry_run else "uninstall"
    return {
        "action": action,
        "removed": removed,
        "keep_vault": keep_vault,
        "path": path,
    }


def hooks_list_data() -> dict[str, Any]:
    """Return structured data about all defined hooks.

    Returns:
        A dict with:
        - ``"hooks"``: list of dicts with ``"name"``, ``"enabled"``,
          ``"event"``, ``"actions"`` keys.
        - ``"supported_events"``: sorted list of supported event names.
        - ``"hooks_dir"``: relative path to hooks directory.
    """
    from vaultspec_core.hooks import SUPPORTED_EVENTS, load_hooks

    hooks = load_hooks(_t.HOOKS_DIR)
    hooks_data = []
    for hook in hooks:
        actions = ", ".join(a.command for a in hook.actions if a.action_type == "shell")
        hooks_data.append(
            {
                "name": hook.name,
                "enabled": hook.enabled,
                "event": hook.event,
                "actions": actions,
            }
        )

    rel = str(_t.HOOKS_DIR.relative_to(_t.TARGET_DIR))
    return {
        "hooks": hooks_data,
        "supported_events": sorted(SUPPORTED_EVENTS),
        "hooks_dir": rel,
    }


def hooks_run(event: str, path: str | None = None) -> list[dict[str, Any]]:
    """Trigger hooks for an event.

    Returns:
        A list of result dicts with ``"hook_name"``, ``"action_type"``,
        ``"success"``, ``"output"``, ``"error"`` keys.

    Raises:
        ProviderError: If the event is not in SUPPORTED_EVENTS.
    """
    from vaultspec_core.hooks import SUPPORTED_EVENTS, load_hooks, trigger

    if event not in SUPPORTED_EVENTS:
        raise ProviderError(
            f"Unknown event: {event}. Supported: {', '.join(sorted(SUPPORTED_EVENTS))}"
        )

    hooks = load_hooks(_t.HOOKS_DIR)
    matching = [h for h in hooks if h.event == event and h.enabled]
    if not matching:
        logger.info("No enabled hooks for event: %s", event)
        return []

    ctx = {"root": str(_t.TARGET_DIR), "event": event}
    if path:
        ctx["path"] = path

    logger.info("Triggering %d hook(s) for '%s'...", len(matching), event)
    results = trigger(hooks, event, ctx)
    return [
        {
            "hook_name": r.hook_name,
            "action_type": r.action_type,
            "success": r.success,
            "output": r.output,
            "error": r.error,
        }
        for r in results
    ]


# Valid sync provider targets exposed to the CLI.
SYNC_PROVIDERS = {"all", "claude", "gemini", "antigravity", "codex"}


def sync_provider(
    provider: str,
    *,
    prune: bool = False,
    dry_run: bool = False,
    force: bool = False,
) -> list[_t.SyncResult]:
    """Sync resources for a single provider target.

    ``provider`` must be one of :data:`SYNC_PROVIDERS`.  The special value
    ``"all"`` syncs every provider and fires post-sync hooks.

    Returns:
        A list of :class:`SyncResult` objects from each sync pass.

    Raises:
        ProviderError: If *provider* is invalid.
        WorkspaceNotInitializedError: If ``.vaultspec/`` does not exist.
        ProviderNotInstalledError: If the specified provider is not installed.
    """
    if provider not in SYNC_PROVIDERS:
        raise ProviderError(
            f"Unknown sync target '{provider}'. "
            f"Valid: {', '.join(sorted(SYNC_PROVIDERS))}"
        )

    from .agents import agents_sync
    from .config_gen import config_sync
    from .rules import rules_sync
    from .skills import skills_sync
    from .system import system_sync

    def _run_all_syncs() -> list[_t.SyncResult]:
        return [
            rules_sync(prune=prune, dry_run=dry_run),
            skills_sync(prune=prune, dry_run=dry_run),
            agents_sync(prune=prune, dry_run=dry_run),
            system_sync(dry_run=dry_run, force=force),
            config_sync(dry_run=dry_run, force=force),
        ]

    # Guard: refuse to sync if vaultspec isn't installed at the target
    vaultspec_dir = _t.TARGET_DIR / ".vaultspec"
    if not vaultspec_dir.exists():
        raise WorkspaceNotInitializedError(
            f"No .vaultspec/ found at {_t.TARGET_DIR}.",
            hint=f"Run 'vaultspec-core install {_t.TARGET_DIR}' first.",
        )

    if provider == "all":
        logger.info("Syncing all resources...")
        results = _run_all_syncs()

        if not dry_run:
            from vaultspec_core.hooks import fire_hooks

            fire_hooks(
                "config.synced",
                {"root": str(_t.TARGET_DIR), "event": "config.synced"},
            )
            logger.info("Done.")
        return results

    # Validate provider is installed
    from .manifest import read_manifest

    installed = read_manifest(_t.TARGET_DIR)
    if installed and provider not in installed:
        raise ProviderNotInstalledError(
            f"Provider '{provider}' is not installed.",
            hint=f"Run 'vaultspec-core install . {provider}' first.",
        )

    # Per-provider sync: filter TOOL_CONFIGS to only the requested tool.
    requested: set[Tool] = set()
    if provider == "claude":
        requested = {Tool.CLAUDE}
    elif provider == "gemini":
        requested = {Tool.GEMINI}
    elif provider == "antigravity":
        requested = {Tool.ANTIGRAVITY}
    elif provider == "codex":
        requested = {Tool.CODEX}

    original = dict(_t.TOOL_CONFIGS)
    try:
        _t.TOOL_CONFIGS = {k: v for k, v in original.items() if k in requested}
        logger.info("Syncing provider: %s ...", provider)
        results = _run_all_syncs()
        if not dry_run:
            logger.info("Done.")
        return results
    finally:
        _t.TOOL_CONFIGS = original

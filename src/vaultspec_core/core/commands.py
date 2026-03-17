"""Implement the top-level operational commands mounted into the root CLI.

This module contains the business logic behind workspace initialization,
install, uninstall, and sync. It sits above the lower-level resource-management
modules and provides the user-facing command behaviors that do not belong
to a dedicated nested Typer namespace.
"""

from __future__ import annotations

import logging
from pathlib import Path

import typer

from . import types as _t
from .enums import ProviderCapability, Tool
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


def init_run(force: bool = False, provider: str = "all") -> None:
    """Scaffold the .vaultspec/ and .vault/ directory structure."""
    from vaultspec_core.config import get_config, reset_config
    from vaultspec_core.config.workspace import resolve_workspace
    from vaultspec_core.core.types import init_paths

    cfg = get_config()
    fw_dir = _t.TARGET_DIR / cfg.framework_dir

    if fw_dir.exists() and not force:
        logger.error("Error: %s already exists. Use --force to overwrite.", fw_dir)
        raise typer.Exit(code=1)

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

    from vaultspec_core.console import get_console

    console = get_console()
    console.print("[bold]Initialized vaultspec-core structure:[/bold]")
    # Deduplicate by relative path, preserving order
    seen: dict[str, str] = {}
    for rel, label in created:
        seen.setdefault(rel, label)
    for rel in seen:
        console.print(f"  {rel}")
    console.print(
        f"Created [bold]{len(seen)}[/bold] directories/files. "
        "Run [bold]vaultspec-core sync[/bold] to sync."
    )


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
) -> None:
    """Deploy the vaultspec framework to a project directory.

    Args:
        path: Target directory.
        provider: Provider to install (``all``, ``core``, ``claude``, etc.).
        upgrade: Re-sync builtin rules without re-scaffolding.
        dry_run: Preview the manifest of files that would be created.
        force: Override contents if installation already exists.
    """
    from vaultspec_core.config import reset_config
    from vaultspec_core.config.workspace import WorkspaceError, resolve_workspace
    from vaultspec_core.console import get_console
    from vaultspec_core.core.types import init_paths

    if provider not in VALID_PROVIDERS:
        logger.error(
            "Unknown provider '%s'. Valid: %s",
            provider,
            ", ".join(sorted(VALID_PROVIDERS)),
        )
        raise typer.Exit(code=1)

    console = get_console()
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

        from .dry_run import DryRunItem, DryRunStatus, render_dry_run_tree

        dry_items = [
            DryRunItem(
                path=str(path / rel).replace("\\", "/"),
                status=(
                    DryRunStatus.EXISTS if (path / rel).exists() else DryRunStatus.NEW
                ),
                label=label,
            )
            for rel, label in seen.items()
        ]
        render_dry_run_tree(dry_items, title=f"Install preview → {path}")
        return

    if upgrade:
        try:
            layout = resolve_workspace(target_override=path)
            init_paths(layout)
        except WorkspaceError as e:
            logger.error("Cannot upgrade: %s", e)
            logger.error("Run 'vaultspec-core install %s' first.", path)
            raise typer.Exit(code=1) from e

        console.print(f"[bold]Upgrading vaultspec framework at {path}[/bold]")

        # Re-seed builtins (force=True overwrites existing)
        from vaultspec_core.builtins import seed_builtins

        fw_dir = path / ".vaultspec"
        seeded = seed_builtins(fw_dir / "rules", force=True)
        if seeded:
            console.print(f"  Re-seeded [bold]{len(seeded)}[/bold] builtin files.")

        # Re-snapshot builtins for revert support
        from .revert import snapshot_builtins

        snapshot_builtins(fw_dir)

        sync_target = provider if provider not in ("all", "core") else "all"
        sync_provider(sync_target, force=True)
        console.print("[bold green]Upgrade complete.[/bold green]")
    else:
        fw_dir = path / ".vaultspec"
        if fw_dir.exists() and not force:
            logger.error(
                "vaultspec is already installed at %s. "
                "Use --upgrade to update, --force to override, or remove it "
                "first with 'vaultspec-core uninstall %s'.",
                path,
                path,
            )
            raise typer.Exit(code=1)

        console.print(f"[bold]Installing vaultspec framework to {path}[/bold]")
        init_run(force=force, provider=provider)

        reset_config()
        layout = resolve_workspace(target_override=path)
        init_paths(layout)

        sync_target = provider if provider not in ("all", "core") else "all"
        sync_provider(sync_target)
        console.print("[bold green]Installation complete.[/bold green]")


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
) -> None:
    """Remove the vaultspec framework from a project directory.

    Args:
        path: Target directory.
        provider: Provider to uninstall (``all``, ``core``, ``<provider>``).
        keep_vault: Preserve ``.vault/`` documentation directory.
        dry_run: Preview what would be removed without deleting.
        force: Required to execute. Uninstall is destructive.
    """
    import shutil

    from vaultspec_core.console import get_console

    from .manifest import providers_sharing_dir, remove_provider

    # Safety gate: require --force for destructive operations
    if not force and not dry_run:
        logger.error(
            "Uninstall is destructive. Pass --force to confirm, "
            "or use --dry-run to preview."
        )
        raise typer.Exit(code=1)

    _t.TARGET_DIR = path
    _ensure_tool_configs(path)

    if provider not in VALID_PROVIDERS:
        logger.error(
            "Unknown provider '%s'. Valid: %s",
            provider,
            ", ".join(sorted(VALID_PROVIDERS)),
        )
        raise typer.Exit(code=1)

    # Uninstalling "core" cascades to all providers
    if provider == "core":
        provider = "all"

    console = get_console()
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

    if provider == "all":
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
        tools = _PROVIDER_TO_TOOLS.get(provider, [])
        for tool in tools:
            dirs, files = _collect_provider_artifacts(path, tool)

            for d in dirs:
                if not d.exists():
                    continue
                # Check if another installed provider still needs this dir
                sharing = providers_sharing_dir(path, d, exclude=provider)
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

    if dry_run:
        from .dry_run import DryRunItem, DryRunStatus, render_dry_run_tree

        dry_items = [
            DryRunItem(path=item_path, status=DryRunStatus.DELETE, label=label)
            for item_path, label in removed
        ]
        render_dry_run_tree(dry_items, title=f"Uninstall preview → {path}")
    elif removed:
        console.print("[bold]Removed vaultspec framework:[/bold]")
        for item_path, _label in removed:
            console.print(f"  {item_path}")
        console.print(f"Removed [bold]{len(removed)}[/bold] items.")
        if keep_vault:
            console.print(
                "[dim].vault/ preserved"
                " (pass --remove-vault to also remove"
                " documentation)[/dim]"
            )
    else:
        console.print("Nothing to remove — vaultspec is not installed at this path.")


def hooks_list() -> None:
    """List all defined hooks."""
    from rich import box
    from rich.table import Table

    from vaultspec_core.console import get_console
    from vaultspec_core.hooks import SUPPORTED_EVENTS, load_hooks

    console = get_console()
    hooks = load_hooks(_t.HOOKS_DIR)
    if not hooks:
        rel = _t.HOOKS_DIR.relative_to(_t.TARGET_DIR)
        console.print("No hooks defined.")
        console.print(f"  Add [dim].yaml[/dim] files to [bold]{rel}/[/bold]")
        console.print(
            "\n[dim]Supported events:[/dim] " + ", ".join(sorted(SUPPORTED_EVENTS))
        )
        return

    table = Table(box=box.SIMPLE_HEAD, highlight=False, show_edge=False)
    table.add_column("Name", no_wrap=True)
    table.add_column("Status")
    table.add_column("Event")
    table.add_column("Actions")

    for hook in hooks:
        if hook.enabled:
            status = "[bold green]enabled[/bold green]"
        else:
            status = "[dim]disabled[/dim]"
        actions = ", ".join(a.command for a in hook.actions if a.action_type == "shell")
        table.add_row(hook.name, status, hook.event, actions)

    console.print(table)


def hooks_run(event: str, path: str | None = None) -> None:
    """Trigger hooks for an event."""
    from vaultspec_core.hooks import SUPPORTED_EVENTS, load_hooks, trigger

    if event not in SUPPORTED_EVENTS:
        logger.error("Unknown event: %s", event)
        logger.error("Supported: %s", ", ".join(sorted(SUPPORTED_EVENTS)))
        raise typer.Exit(code=1)

    hooks = load_hooks(_t.HOOKS_DIR)
    matching = [h for h in hooks if h.event == event and h.enabled]
    if not matching:
        logger.info("No enabled hooks for event: %s", event)
        return

    ctx = {"root": str(_t.TARGET_DIR), "event": event}
    if path:
        ctx["path"] = path

    from vaultspec_core.console import get_console

    console = get_console()
    logger.info("Triggering %d hook(s) for '%s'...", len(matching), event)
    results = trigger(hooks, event, ctx)
    for r in results:
        if r.success:
            icon = "[bold green]OK[/bold green]"
        else:
            icon = "[bold red]FAIL[/bold red]"
        console.print(f"  {r.hook_name} ({r.action_type}): {icon}")
        if r.output:
            for line in r.output.splitlines()[:5]:
                console.print(f"    {line}")
        if r.error:
            console.print(f"    [red]error:[/red] {r.error}")


# Valid sync provider targets exposed to the CLI.
SYNC_PROVIDERS = {"all", "claude", "gemini", "antigravity", "codex"}


def sync_provider(
    provider: str,
    *,
    prune: bool = False,
    dry_run: bool = False,
    force: bool = False,
) -> None:
    """Sync resources for a single provider target.

    ``provider`` must be one of :data:`SYNC_PROVIDERS`.  The special value
    ``"all"`` syncs every provider and fires post-sync hooks.
    """
    if provider not in SYNC_PROVIDERS:
        logger.error(
            "Unknown sync target '%s'. Valid: %s",
            provider,
            ", ".join(sorted(SYNC_PROVIDERS)),
        )
        raise typer.Exit(code=1)

    from .agents import agents_sync
    from .config_gen import config_sync
    from .enums import Tool
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

    def _infer_label(item_path: str) -> str:
        """Infer a human-readable label from a sync output path."""
        # Normalise to forward slashes for matching
        p = item_path.replace("\\", "/")

        # Provider detection from path segments
        provider_map = {
            "/.claude/": "claude",
            "/.gemini/": "gemini",
            "/.agents/": "antigravity",
            "/.codex/": "codex",
        }
        provider_name = ""
        for segment, name in provider_map.items():
            if segment in p:
                provider_name = name
                break

        # Config files at root level
        config_map = {
            "/CLAUDE.md": "claude (config)",
            "/GEMINI.md": "gemini (config)",
            "/AGENTS.md": "codex (config)",
            "/config.toml": "codex (config)",
        }
        for suffix, lbl in config_map.items():
            if p.endswith(suffix):
                return lbl

        # Resource type detection
        if "/rules/" in p:
            return f"{provider_name} (rules)" if provider_name else "rules"
        if "/skills/" in p:
            return f"{provider_name} (skills)" if provider_name else "skills"
        if "/agents/" in p:
            return f"{provider_name} (agents)" if provider_name else "agents"
        if "SYSTEM.md" in p or "system" in p.lower():
            return f"{provider_name} (system)" if provider_name else "system"

        return provider_name or ""

    def _render_dry_tree(results: list[_t.SyncResult], title: str) -> None:
        from .dry_run import DryRunItem, DryRunStatus, render_dry_run_tree

        action_map = {
            "[ADD]": DryRunStatus.NEW,
            "[UPDATE]": DryRunStatus.UPDATE,
            "[DELETE]": DryRunStatus.DELETE,
        }
        all_items = []
        for r in results:
            for item_path, action in r.items:
                status = action_map.get(action, DryRunStatus.UPDATE)
                all_items.append(
                    DryRunItem(
                        path=item_path,
                        status=status,
                        label=_infer_label(item_path),
                    )
                )
        if all_items:
            render_dry_run_tree(all_items, title=title)
        else:
            from vaultspec_core.console import get_console

            get_console().print(f"[dim]{title}: no changes[/dim]")

    # Guard: refuse to sync if vaultspec isn't installed at the target
    vaultspec_dir = _t.TARGET_DIR / ".vaultspec"
    if not vaultspec_dir.exists():
        logger.error(
            "No .vaultspec/ found at %s. Run 'vaultspec-core install %s' first.",
            _t.TARGET_DIR,
            _t.TARGET_DIR,
        )
        raise typer.Exit(code=1)

    def _warn_if_empty(results: list[_t.SyncResult]) -> None:
        total_changes = sum(r.added + r.updated for r in results)
        total_skipped = sum(r.skipped for r in results)
        if total_changes == 0 and total_skipped == 0:
            from vaultspec_core.console import get_console

            console = get_console()
            console.print(
                "[bold yellow]Warning:[/bold yellow] Sync produced 0 files. "
                "The .vaultspec/rules/ source directories may be empty.\n"
                "  Run [bold]vaultspec-core install . --upgrade[/bold] "
                "to re-seed builtin content."
            )

    if provider == "all":
        logger.info("Syncing all resources...")
        results = _run_all_syncs()

        if dry_run:
            _render_dry_tree(results, f"Sync preview → {_t.TARGET_DIR}")
        else:
            _warn_if_empty(results)
            from vaultspec_core.hooks import fire_hooks

            fire_hooks(
                "config.synced",
                {"root": str(_t.TARGET_DIR), "event": "config.synced"},
            )
            logger.info("Done.")
        return

    # Validate provider is installed (skip if .vaultspec/ doesn't exist yet,
    # which happens during install_run before the first sync).
    from .manifest import read_manifest

    installed = read_manifest(_t.TARGET_DIR)
    if installed and provider not in installed:
        logger.error(
            "Provider '%s' is not installed. Run 'vaultspec-core install . %s' first.",
            provider,
            provider,
        )
        raise typer.Exit(code=1)

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

        if dry_run:
            _render_dry_tree(results, f"Sync preview ({provider}) → {_t.TARGET_DIR}")
        else:
            logger.info("Done.")
    finally:
        _t.TOOL_CONFIGS = original

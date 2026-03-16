"""Define the resource-management command surface mounted under the root CLI.

This module exposes the framework-resource and maintenance command families for
rules, skills, agents, config, system, hooks, initialization, readiness,
doctoring, and test execution by delegating into the `core` resource-management
layer.

Usage:
    Use this module through the root CLI for the non-vault command families,
    including rules, skills, agents, config, system, hooks, and maintenance
    commands such as `init`, `doctor`, `readiness`, and `test`.
"""

from __future__ import annotations

import logging
from pathlib import Path  # noqa: TC003 — Typer needs Path at runtime
from typing import Annotated

import typer

from .core import (
    agents_add,
    agents_list,
    agents_sync,
    config_show,
    config_sync,
    resource_edit,
    resource_remove,
    resource_rename,
    resource_show,
    rules_add,
    rules_list,
    rules_sync,
    skills_add,
    skills_list,
    skills_sync,
    system_show,
    system_sync,
)
from .core import types as _t
from .core.commands import (
    doctor_run,
    hooks_list,
    hooks_run,
    init_run,
    readiness_run,
    test_run,
)

logger = logging.getLogger(__name__)

spec_app = typer.Typer(
    help=(
        "Manage framework resources, synced outputs, hooks, and workspace maintenance."
    ),
    no_args_is_help=True,
)

# --- rules ---
rules_app = typer.Typer(help="Manage framework rule sources and synced rule outputs")
spec_app.add_typer(rules_app, name="rules")


@rules_app.command("list")
def cmd_rules_list():
    """List all available rules."""
    rules_list()


@rules_app.command("add")
def cmd_rules_add(
    name: Annotated[str, typer.Option("--name", help="Rule name")],
    content: Annotated[
        str | None, typer.Option("--content", help="Rule content")
    ] = None,
    force: Annotated[bool, typer.Option("--force", help="Overwrite existing")] = False,
):
    """Add a new custom rule."""
    rules_add(name=name, content=content, force=force)


@rules_app.command("show")
def cmd_rules_show(name: Annotated[str, typer.Argument(help="Rule name")]):
    """Display a rule's content."""
    resource_show(name=name, base_dir=_t.RULES_SRC_DIR, label="Rule")


@rules_app.command("edit")
def cmd_rules_edit(name: Annotated[str, typer.Argument(help="Rule name")]):
    """Open a rule in the configured editor."""
    resource_edit(name=name, base_dir=_t.RULES_SRC_DIR, label="Rule")


@rules_app.command("remove")
def cmd_rules_remove(
    name: Annotated[str, typer.Argument(help="Rule name")],
    force: Annotated[bool, typer.Option("--force", help="Skip confirmation")] = False,
):
    """Delete a rule."""
    resource_remove(name=name, base_dir=_t.RULES_SRC_DIR, label="Rule", force=force)


@rules_app.command("rename")
def cmd_rules_rename(
    old_name: Annotated[str, typer.Argument(help="Current rule name")],
    new_name: Annotated[str, typer.Argument(help="New rule name")],
):
    """Rename an existing rule."""
    resource_rename(
        old_name=old_name, new_name=new_name, base_dir=_t.RULES_SRC_DIR, label="Rule"
    )


@rules_app.command("sync")
def cmd_rules_sync(
    prune: Annotated[bool, typer.Option("--prune", help="Remove stale files")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview changes")] = False,
):
    """Sync rules to tool destinations."""
    rules_sync(prune=prune, dry_run=dry_run)


# --- skills ---
skills_app = typer.Typer(help="Manage workflow skills and synced skill outputs")
spec_app.add_typer(skills_app, name="skills")


@skills_app.command("list")
def cmd_skills_list():
    """List all available skills."""
    skills_list()


@skills_app.command("add")
def cmd_skills_add(
    name: Annotated[str, typer.Option("--name", help="Skill name")],
    description: Annotated[
        str, typer.Option("--description", help="Skill description")
    ] = "",
    force: Annotated[bool, typer.Option("--force", help="Overwrite existing")] = False,
    template: Annotated[
        str | None, typer.Option("--template", help="Template to use")
    ] = None,
):
    """Add a new skill."""
    skills_add(name=name, description=description, force=force, template=template)


@skills_app.command("show")
def cmd_skills_show(name: Annotated[str, typer.Argument(help="Skill name")]):
    """Display a skill's content."""
    resource_show(name=name, base_dir=_t.SKILLS_SRC_DIR, label="Skill")


@skills_app.command("edit")
def cmd_skills_edit(name: Annotated[str, typer.Argument(help="Skill name")]):
    """Open a skill in the configured editor."""
    resource_edit(name=name, base_dir=_t.SKILLS_SRC_DIR, label="Skill")


@skills_app.command("remove")
def cmd_skills_remove(
    name: Annotated[str, typer.Argument(help="Skill name")],
    force: Annotated[bool, typer.Option("--force", help="Skip confirmation")] = False,
):
    """Delete a skill."""
    resource_remove(name=name, base_dir=_t.SKILLS_SRC_DIR, label="Skill", force=force)


@skills_app.command("rename")
def cmd_skills_rename(
    old_name: Annotated[str, typer.Argument(help="Current skill name")],
    new_name: Annotated[str, typer.Argument(help="New skill name")],
):
    """Rename an existing skill."""
    resource_rename(
        old_name=old_name, new_name=new_name, base_dir=_t.SKILLS_SRC_DIR, label="Skill"
    )


@skills_app.command("sync")
def cmd_skills_sync(
    prune: Annotated[bool, typer.Option("--prune", help="Remove stale files")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview changes")] = False,
):
    """Sync skills to tool destinations."""
    skills_sync(prune=prune, dry_run=dry_run)


# --- agents ---
agents_app = typer.Typer(help="Manage agent definitions and synced agent outputs")
spec_app.add_typer(agents_app, name="agents")


@agents_app.command("list")
def cmd_agents_list():
    """List all available agents."""
    agents_list()


@agents_app.command("add")
def cmd_agents_add(
    name: Annotated[str, typer.Option("--name", help="Agent name")],
    description: Annotated[
        str, typer.Option("--description", help="Agent description")
    ] = "",
    force: Annotated[bool, typer.Option("--force", help="Overwrite existing")] = False,
):
    """Add a new agent definition."""
    agents_add(name=name, description=description, force=force)


@agents_app.command("show")
def cmd_agents_show(name: Annotated[str, typer.Argument(help="Agent name")]):
    """Display an agent's content."""
    resource_show(name=name, base_dir=_t.AGENTS_SRC_DIR, label="Agent")


@agents_app.command("edit")
def cmd_agents_edit(name: Annotated[str, typer.Argument(help="Agent name")]):
    """Open an agent in the configured editor."""
    resource_edit(name=name, base_dir=_t.AGENTS_SRC_DIR, label="Agent")


@agents_app.command("remove")
def cmd_agents_remove(
    name: Annotated[str, typer.Argument(help="Agent name")],
    force: Annotated[bool, typer.Option("--force", help="Skip confirmation")] = False,
):
    """Delete an agent definition."""
    resource_remove(name=name, base_dir=_t.AGENTS_SRC_DIR, label="Agent", force=force)


@agents_app.command("rename")
def cmd_agents_rename(
    old_name: Annotated[str, typer.Argument(help="Current agent name")],
    new_name: Annotated[str, typer.Argument(help="New agent name")],
):
    """Rename an existing agent definition."""
    resource_rename(
        old_name=old_name, new_name=new_name, base_dir=_t.AGENTS_SRC_DIR, label="Agent"
    )


@agents_app.command("sync")
def cmd_agents_sync(
    prune: Annotated[bool, typer.Option("--prune", help="Remove stale files")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview changes")] = False,
):
    """Sync agents to tool destinations."""
    agents_sync(prune=prune, dry_run=dry_run)


# --- config ---
config_app = typer.Typer(help="Inspect and sync tool-facing configuration files")
spec_app.add_typer(config_app, name="config")


@config_app.command("show")
def cmd_config_show():
    """Display generated tool configurations."""
    config_show()


@config_app.command("sync")
def cmd_config_sync(
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview changes")] = False,
    force: Annotated[
        bool, typer.Option("--force", help="Overwrite non-managed files")
    ] = False,
):
    """Sync configurations to tool destinations."""
    config_sync(dry_run=dry_run, force=force)


# --- system ---
system_app = typer.Typer(help="Inspect and sync assembled system prompt outputs")
spec_app.add_typer(system_app, name="system")


@system_app.command("show")
def cmd_system_show():
    """Display system prompt parts and targets."""
    system_show()


@system_app.command("sync")
def cmd_system_sync(
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview changes")] = False,
    force: Annotated[
        bool, typer.Option("--force", help="Overwrite non-managed files")
    ] = False,
):
    """Sync system prompts to tool destinations."""
    system_sync(dry_run=dry_run, force=force)


# --- top level commands ---

# Valid sync provider targets exposed to the CLI.
_SYNC_PROVIDERS = {"all", "claude", "gemini", "antigravity", "codex"}


def _sync_provider(
    provider: str,
    *,
    prune: bool = False,
    dry_run: bool = False,
    force: bool = False,
) -> None:
    """Sync resources for a single provider target.

    ``provider`` must be one of :data:`_SYNC_PROVIDERS`.  The special value
    ``"all"`` syncs every provider and fires post-sync hooks.
    """
    from .core.enums import Tool

    if provider == "all":
        logger.info("Syncing all resources...")
        rules_sync(prune=prune, dry_run=dry_run)
        skills_sync(prune=prune, dry_run=dry_run)
        agents_sync(prune=prune, dry_run=dry_run)
        system_sync(dry_run=dry_run, force=force)
        config_sync(dry_run=dry_run, force=force)

        from .hooks import fire_hooks

        fire_hooks(
            "config.synced", {"root": str(_t.TARGET_DIR), "event": "config.synced"}
        )
        logger.info("Done.")
        return

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
        rules_sync(prune=prune, dry_run=dry_run)
        skills_sync(prune=prune, dry_run=dry_run)
        agents_sync(prune=prune, dry_run=dry_run)
        system_sync(dry_run=dry_run, force=force)
        config_sync(dry_run=dry_run, force=force)
        logger.info("Done.")
    finally:
        _t.TOOL_CONFIGS = original


@spec_app.command("sync")
def cmd_sync(
    provider: Annotated[
        str,
        typer.Argument(
            help="Provider to sync (all, claude, gemini, antigravity, codex)"
        ),
    ] = "all",
    prune: Annotated[bool, typer.Option("--prune", help="Remove stale files")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview changes")] = False,
    force: Annotated[
        bool, typer.Option("--force", help="Overwrite non-managed files")
    ] = False,
):
    """Sync rules, skills, agents, configs, and system prompts.

    Defaults to syncing all providers.  Pass a provider name to sync only
    that provider (e.g. ``vaultspec-core sync claude``).
    """
    if provider not in _SYNC_PROVIDERS:
        valid = ", ".join(sorted(_SYNC_PROVIDERS))
        logger.error("Unknown sync provider '%s'. Valid: %s", provider, valid)
        raise typer.Exit(code=1)
    _sync_provider(provider, prune=prune, dry_run=dry_run, force=force)


@spec_app.command("install")
def cmd_install(
    path: Annotated[
        Path,
        typer.Argument(
            help="Target directory (use '.' for current directory)",
            exists=True,
            dir_okay=True,
            file_okay=False,
            resolve_path=True,
        ),
    ],
    provider: Annotated[
        str,
        typer.Argument(
            help="Provider to install (all, core, claude, gemini, antigravity, codex)"
        ),
    ] = "all",
    upgrade: Annotated[
        bool,
        typer.Option("--upgrade", help="Re-sync builtin rules and firmware"),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Preview changes without writing"),
    ] = False,
):
    """Deploy the vaultspec framework to a project directory.

    Scaffolds the workspace structure and syncs all managed resources.
    Use --upgrade to update builtin rules without re-scaffolding.

    Examples:\n
      vaultspec-core install .                    # install all providers\n
      vaultspec-core install . core               # framework only, no providers\n
      vaultspec-core install . claude             # framework + claude\n
      vaultspec-core install . --upgrade          # update firmware + re-sync\n
      vaultspec-core install . claude --dry-run   # preview what would be created\n
    """
    from .core.commands import install_run

    install_run(path=path, provider=provider, upgrade=upgrade, dry_run=dry_run)


@spec_app.command("uninstall")
def cmd_uninstall(
    path: Annotated[
        Path,
        typer.Argument(
            help="Target directory to remove vaultspec from",
            exists=True,
            dir_okay=True,
            file_okay=False,
            resolve_path=True,
        ),
    ],
    provider: Annotated[
        str,
        typer.Argument(
            help="Provider to uninstall (all, core, claude, gemini, antigravity, codex)"
        ),
    ] = "all",
    keep_vault: Annotated[
        bool,
        typer.Option("--keep-vault", help="Preserve .vault/ documentation"),
    ] = False,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Preview changes without removing")
    ] = False,
):
    """Remove the vaultspec framework from a project directory.

    Removes all managed artifacts (.vaultspec/, provider dirs, generated configs).
    Use a provider name to remove only that provider's artifacts.

    Examples:\n
      vaultspec-core uninstall .                  # remove everything\n
      vaultspec-core uninstall . claude           # remove only claude\n
      vaultspec-core uninstall . --dry-run        # preview what would be removed\n
    """
    from .core.commands import uninstall_run

    uninstall_run(path=path, provider=provider, keep_vault=keep_vault, dry_run=dry_run)


@spec_app.command("test")
def cmd_test(
    category: Annotated[
        str, typer.Option("--category", "-c", help="Test category (unit, api, etc.)")
    ] = "all",
    module: Annotated[
        str | None, typer.Option("--module", "-m", help="Filter by module")
    ] = None,
    extra_args: Annotated[
        list[str] | None, typer.Argument(help="Extra pytest args")
    ] = None,
):
    """Run the packaged test surface with optional pytest passthrough."""
    test_run(category=category, module=module, extra_args=extra_args)


@spec_app.command("doctor")
def cmd_doctor():
    """Check prerequisites and system health."""
    doctor_run()


@spec_app.command("init")
def cmd_init(
    force: Annotated[
        bool, typer.Option("--force", help="Overwrite existing structure")
    ] = False,
    provider: Annotated[
        str,
        typer.Argument(
            help="Provider to scaffold (all, core, claude, gemini, antigravity, codex)"
        ),
    ] = "all",
):
    """Initialize or normalize a workspace scaffold."""
    init_run(force=force, provider=provider)


@spec_app.command("readiness")
def cmd_readiness(
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
):
    """Assess workspace readiness and governance coverage."""
    readiness_run(json_output=json_output)


# --- hooks ---
hooks_app = typer.Typer(help="List and run shell-based workspace hooks")
spec_app.add_typer(hooks_app, name="hooks")


@hooks_app.command("list")
def cmd_hooks_list():
    """List all defined hooks."""
    hooks_list()


@hooks_app.command("run")
def cmd_hooks_run(
    event: Annotated[str, typer.Argument(help="Event name")],
    path: Annotated[
        str | None, typer.Option("--path", help="Context path variable")
    ] = None,
):
    """Trigger hooks for a specific event."""
    hooks_run(event=event, path=path)

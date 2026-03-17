"""Spec command group -- manage framework resources.

Covers rules, skills, agents, system prompts, and hooks. Delegates to
existing core backend functions via lazy imports to avoid circular
import issues.
"""

from __future__ import annotations

import logging
from typing import Annotated

import typer

logger = logging.getLogger(__name__)

spec_app = typer.Typer(
    help=(
        "Manage framework resources: rules, skills, agents, system prompts, and hooks."
    ),
    no_args_is_help=True,
)


# =============================================================================
# Rules
# =============================================================================

rules_app = typer.Typer(
    help="Manage framework rule sources and synced rule outputs.",
    no_args_is_help=True,
)
spec_app.add_typer(rules_app, name="rules")


@rules_app.command("list")
def cmd_rules_list() -> None:
    """List all available rules."""
    from vaultspec_core.core import rules_list

    rules_list()


@rules_app.command("add")
def cmd_rules_add(
    name: Annotated[str, typer.Option("--name", help="Rule name")],
    content: Annotated[
        str | None, typer.Option("--content", help="Rule content")
    ] = None,
    force: Annotated[bool, typer.Option("--force", help="Overwrite existing")] = False,
) -> None:
    """Add a new custom rule."""
    from vaultspec_core.core import rules_add

    rules_add(name=name, content=content, force=force)


@rules_app.command("show")
def cmd_rules_show(name: Annotated[str, typer.Argument(help="Rule name")]) -> None:
    """Display a rule's content."""
    from vaultspec_core.core import resource_show
    from vaultspec_core.core import types as _t

    resource_show(name=name, base_dir=_t.RULES_SRC_DIR, label="Rule")


@rules_app.command("edit")
def cmd_rules_edit(name: Annotated[str, typer.Argument(help="Rule name")]) -> None:
    """Open a rule in the configured editor."""
    from vaultspec_core.core import resource_edit
    from vaultspec_core.core import types as _t

    resource_edit(name=name, base_dir=_t.RULES_SRC_DIR, label="Rule")


@rules_app.command("remove")
def cmd_rules_remove(
    name: Annotated[str, typer.Argument(help="Rule name")],
    force: Annotated[bool, typer.Option("--force", help="Skip confirmation")] = False,
) -> None:
    """Delete a rule."""
    from vaultspec_core.core import resource_remove
    from vaultspec_core.core import types as _t

    resource_remove(name=name, base_dir=_t.RULES_SRC_DIR, label="Rule", force=force)


@rules_app.command("rename")
def cmd_rules_rename(
    old_name: Annotated[str, typer.Argument(help="Current rule name")],
    new_name: Annotated[str, typer.Argument(help="New rule name")],
) -> None:
    """Rename an existing rule."""
    from vaultspec_core.core import resource_rename
    from vaultspec_core.core import types as _t

    resource_rename(
        old_name=old_name, new_name=new_name, base_dir=_t.RULES_SRC_DIR, label="Rule"
    )


@rules_app.command("sync")
def cmd_rules_sync(
    prune: Annotated[bool, typer.Option("--prune", help="Remove stale files")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview changes")] = False,
) -> None:
    """Sync rules to tool destinations."""
    from vaultspec_core.core import rules_sync

    rules_sync(prune=prune, dry_run=dry_run)


@rules_app.command("revert")
def cmd_rules_revert(
    filename: Annotated[str, typer.Argument(help="Rule filename to revert")],
) -> None:
    """Revert a rule to its snapshotted original."""
    from vaultspec_core.core import types as _t
    from vaultspec_core.core.revert import revert_resource

    vaultspec_dir = _t.TARGET_DIR / ".vaultspec"
    if not filename.endswith(".md"):
        filename = f"{filename}.md"
    result = revert_resource(vaultspec_dir, "rules", filename)
    if result.get("reverted"):
        typer.echo(f"Reverted rule: {filename}")
    else:
        msg = result.get("reason", f"No snapshot found for rule: {filename}")
        typer.echo(msg, err=True)
        raise typer.Exit(code=1)


# =============================================================================
# Skills
# =============================================================================

skills_app = typer.Typer(
    help="Manage workflow skills and synced skill outputs.",
    no_args_is_help=True,
)
spec_app.add_typer(skills_app, name="skills")


@skills_app.command("list")
def cmd_skills_list() -> None:
    """List all available skills."""
    from vaultspec_core.core import skills_list

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
) -> None:
    """Add a new skill."""
    from vaultspec_core.core import skills_add

    skills_add(name=name, description=description, force=force, template=template)


@skills_app.command("show")
def cmd_skills_show(name: Annotated[str, typer.Argument(help="Skill name")]) -> None:
    """Display a skill's content."""
    from vaultspec_core.core import resource_show
    from vaultspec_core.core import types as _t

    resource_show(name=name, base_dir=_t.SKILLS_SRC_DIR, label="Skill", is_dir=True)


@skills_app.command("edit")
def cmd_skills_edit(name: Annotated[str, typer.Argument(help="Skill name")]) -> None:
    """Open a skill in the configured editor."""
    from vaultspec_core.core import resource_edit
    from vaultspec_core.core import types as _t

    resource_edit(name=name, base_dir=_t.SKILLS_SRC_DIR, label="Skill", is_dir=True)


@skills_app.command("remove")
def cmd_skills_remove(
    name: Annotated[str, typer.Argument(help="Skill name")],
    force: Annotated[bool, typer.Option("--force", help="Skip confirmation")] = False,
) -> None:
    """Delete a skill."""
    from vaultspec_core.core import resource_remove
    from vaultspec_core.core import types as _t

    resource_remove(
        name=name, base_dir=_t.SKILLS_SRC_DIR, label="Skill", force=force, is_dir=True
    )


@skills_app.command("rename")
def cmd_skills_rename(
    old_name: Annotated[str, typer.Argument(help="Current skill name")],
    new_name: Annotated[str, typer.Argument(help="New skill name")],
) -> None:
    """Rename an existing skill."""
    from vaultspec_core.core import resource_rename
    from vaultspec_core.core import types as _t

    resource_rename(
        old_name=old_name,
        new_name=new_name,
        base_dir=_t.SKILLS_SRC_DIR,
        label="Skill",
        is_dir=True,
    )


@skills_app.command("sync")
def cmd_skills_sync(
    prune: Annotated[bool, typer.Option("--prune", help="Remove stale files")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview changes")] = False,
) -> None:
    """Sync skills to tool destinations."""
    from vaultspec_core.core import skills_sync

    skills_sync(prune=prune, dry_run=dry_run)


@skills_app.command("revert")
def cmd_skills_revert(
    filename: Annotated[str, typer.Argument(help="Skill filename to revert")],
) -> None:
    """Revert a skill to its snapshotted original."""
    from vaultspec_core.core import types as _t
    from vaultspec_core.core.revert import revert_resource

    vaultspec_dir = _t.TARGET_DIR / ".vaultspec"
    if not filename.endswith(".md"):
        filename = f"{filename}.md"
    result = revert_resource(vaultspec_dir, "skills", filename)
    if result.get("reverted"):
        typer.echo(f"Reverted skill: {filename}")
    else:
        msg = result.get("reason", f"No snapshot found for skill: {filename}")
        typer.echo(msg, err=True)
        raise typer.Exit(code=1)


# =============================================================================
# Agents
# =============================================================================

agents_app = typer.Typer(
    help="Manage agent definitions and synced agent outputs.",
    no_args_is_help=True,
)
spec_app.add_typer(agents_app, name="agents")


@agents_app.command("list")
def cmd_agents_list() -> None:
    """List all available agents."""
    from vaultspec_core.core import agents_list

    agents_list()


@agents_app.command("add")
def cmd_agents_add(
    name: Annotated[str, typer.Option("--name", help="Agent name")],
    description: Annotated[
        str, typer.Option("--description", help="Agent description")
    ] = "",
    force: Annotated[bool, typer.Option("--force", help="Overwrite existing")] = False,
) -> None:
    """Add a new agent definition."""
    from vaultspec_core.core import agents_add

    agents_add(name=name, description=description, force=force)


@agents_app.command("show")
def cmd_agents_show(name: Annotated[str, typer.Argument(help="Agent name")]) -> None:
    """Display an agent's content."""
    from vaultspec_core.core import resource_show
    from vaultspec_core.core import types as _t

    resource_show(name=name, base_dir=_t.AGENTS_SRC_DIR, label="Agent")


@agents_app.command("edit")
def cmd_agents_edit(name: Annotated[str, typer.Argument(help="Agent name")]) -> None:
    """Open an agent in the configured editor."""
    from vaultspec_core.core import resource_edit
    from vaultspec_core.core import types as _t

    resource_edit(name=name, base_dir=_t.AGENTS_SRC_DIR, label="Agent")


@agents_app.command("remove")
def cmd_agents_remove(
    name: Annotated[str, typer.Argument(help="Agent name")],
    force: Annotated[bool, typer.Option("--force", help="Skip confirmation")] = False,
) -> None:
    """Delete an agent definition."""
    from vaultspec_core.core import resource_remove
    from vaultspec_core.core import types as _t

    resource_remove(name=name, base_dir=_t.AGENTS_SRC_DIR, label="Agent", force=force)


@agents_app.command("rename")
def cmd_agents_rename(
    old_name: Annotated[str, typer.Argument(help="Current agent name")],
    new_name: Annotated[str, typer.Argument(help="New agent name")],
) -> None:
    """Rename an existing agent definition."""
    from vaultspec_core.core import resource_rename
    from vaultspec_core.core import types as _t

    resource_rename(
        old_name=old_name, new_name=new_name, base_dir=_t.AGENTS_SRC_DIR, label="Agent"
    )


@agents_app.command("sync")
def cmd_agents_sync(
    prune: Annotated[bool, typer.Option("--prune", help="Remove stale files")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview changes")] = False,
) -> None:
    """Sync agents to tool destinations."""
    from vaultspec_core.core import agents_sync

    agents_sync(prune=prune, dry_run=dry_run)


@agents_app.command("revert")
def cmd_agents_revert(
    filename: Annotated[str, typer.Argument(help="Agent filename to revert")],
) -> None:
    """Revert an agent to its snapshotted original."""
    from vaultspec_core.core import types as _t
    from vaultspec_core.core.revert import revert_resource

    vaultspec_dir = _t.TARGET_DIR / ".vaultspec"
    if not filename.endswith(".md"):
        filename = f"{filename}.md"
    result = revert_resource(vaultspec_dir, "agents", filename)
    if result.get("reverted"):
        typer.echo(f"Reverted agent: {filename}")
    else:
        msg = result.get("reason", f"No snapshot found for agent: {filename}")
        typer.echo(msg, err=True)
        raise typer.Exit(code=1)


# =============================================================================
# System
# =============================================================================

system_app = typer.Typer(
    help="Inspect and sync assembled system prompt outputs.",
    no_args_is_help=True,
)
spec_app.add_typer(system_app, name="system")


@system_app.command("show")
def cmd_system_show() -> None:
    """Display system prompt parts and targets."""
    from vaultspec_core.core import system_show

    system_show()


@system_app.command("sync")
def cmd_system_sync(
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview changes")] = False,
    force: Annotated[
        bool, typer.Option("--force", help="Overwrite non-managed files")
    ] = False,
) -> None:
    """Sync system prompts to tool destinations."""
    from vaultspec_core.core import system_sync

    system_sync(dry_run=dry_run, force=force)


# =============================================================================
# Hooks
# =============================================================================

hooks_app = typer.Typer(
    help="List and run shell-based workspace hooks.",
    no_args_is_help=True,
)
spec_app.add_typer(hooks_app, name="hooks")


@hooks_app.command("list")
def cmd_hooks_list() -> None:
    """List all defined hooks."""
    from vaultspec_core.core.commands import hooks_list

    hooks_list()


@hooks_app.command("run")
def cmd_hooks_run(
    event: Annotated[str, typer.Argument(help="Event name")],
    path: Annotated[
        str | None, typer.Option("--path", help="Context path variable")
    ] = None,
) -> None:
    """Trigger hooks for a specific event."""
    from vaultspec_core.core.commands import hooks_run

    hooks_run(event=event, path=path)

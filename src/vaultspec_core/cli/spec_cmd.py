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


def _handle_error(exc: Exception) -> None:
    """Convert a domain exception to a CLI error exit."""
    from vaultspec_core.core.exceptions import VaultSpecError

    if isinstance(exc, VaultSpecError):
        typer.echo(f"Error: {exc}", err=True)
        if exc.hint:
            typer.echo(f"  Hint: {exc.hint}", err=True)
        raise typer.Exit(code=1) from exc
    raise exc


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
    from rich import box
    from rich.table import Table

    from vaultspec_core.console import get_console
    from vaultspec_core.core import rules_list

    table = Table(box=box.SIMPLE_HEAD, highlight=False, show_edge=False)
    table.add_column("Name", no_wrap=True)
    table.add_column("Source")

    for item in rules_list():
        table.add_row(item["name"], item["source"])

    get_console().print(table)


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
    from vaultspec_core.core.exceptions import VaultSpecError

    try:
        rules_add(name=name, content=content, force=force)
    except VaultSpecError as exc:
        _handle_error(exc)


@rules_app.command("show")
def cmd_rules_show(name: Annotated[str, typer.Argument(help="Rule name")]) -> None:
    """Display a rule's content."""
    from vaultspec_core.core import resource_show
    from vaultspec_core.core import types as _t
    from vaultspec_core.core.exceptions import VaultSpecError

    try:
        content = resource_show(name=name, base_dir=_t.RULES_SRC_DIR, label="Rule")
        typer.echo(content)
    except VaultSpecError as exc:
        _handle_error(exc)


@rules_app.command("edit")
def cmd_rules_edit(name: Annotated[str, typer.Argument(help="Rule name")]) -> None:
    """Open a rule in the configured editor."""
    from vaultspec_core.core import resource_edit
    from vaultspec_core.core import types as _t
    from vaultspec_core.core.exceptions import VaultSpecError

    try:
        resource_edit(name=name, base_dir=_t.RULES_SRC_DIR, label="Rule")
    except VaultSpecError as exc:
        _handle_error(exc)


@rules_app.command("remove")
def cmd_rules_remove(
    name: Annotated[str, typer.Argument(help="Rule name")],
    force: Annotated[bool, typer.Option("--force", help="Skip confirmation")] = False,
) -> None:
    """Delete a rule."""
    from vaultspec_core.core import resource_remove
    from vaultspec_core.core import types as _t
    from vaultspec_core.core.exceptions import VaultSpecError

    try:
        resource_remove(
            name=name,
            base_dir=_t.RULES_SRC_DIR,
            label="Rule",
            force=force,
            confirm_fn=typer.confirm,
        )
    except VaultSpecError as exc:
        _handle_error(exc)


@rules_app.command("rename")
def cmd_rules_rename(
    old_name: Annotated[str, typer.Argument(help="Current rule name")],
    new_name: Annotated[str, typer.Argument(help="New rule name")],
) -> None:
    """Rename an existing rule."""
    from vaultspec_core.core import resource_rename
    from vaultspec_core.core import types as _t
    from vaultspec_core.core.exceptions import VaultSpecError

    try:
        resource_rename(
            old_name=old_name,
            new_name=new_name,
            base_dir=_t.RULES_SRC_DIR,
            label="Rule",
        )
    except VaultSpecError as exc:
        _handle_error(exc)


@rules_app.command("sync")
def cmd_rules_sync(
    prune: Annotated[bool, typer.Option("--prune", help="Remove stale files")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview changes")] = False,
) -> None:
    """Sync rules to tool destinations."""
    from vaultspec_core.console import get_console
    from vaultspec_core.core import rules_sync
    from vaultspec_core.core.sync import format_summary

    result = rules_sync(prune=prune, dry_run=dry_run)
    get_console().print(f"  [bold]{format_summary('Rules', result)}[/bold]")


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
    from rich import box
    from rich.table import Table

    from vaultspec_core.console import get_console
    from vaultspec_core.core import skills_list

    items = skills_list()
    console = get_console()
    if not items:
        console.print("No managed skills found.")
        return

    table = Table(box=box.SIMPLE_HEAD, highlight=False, show_edge=False)
    table.add_column("Name", no_wrap=True)
    table.add_column("Description", max_width=60, overflow="ellipsis")

    for item in items:
        table.add_row(item["name"], item["description"])

    console.print(table)


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
    from vaultspec_core.core.exceptions import VaultSpecError

    try:
        skills_add(name=name, description=description, force=force, template=template)
    except VaultSpecError as exc:
        _handle_error(exc)


@skills_app.command("show")
def cmd_skills_show(name: Annotated[str, typer.Argument(help="Skill name")]) -> None:
    """Display a skill's content."""
    from vaultspec_core.core import resource_show
    from vaultspec_core.core import types as _t
    from vaultspec_core.core.exceptions import VaultSpecError

    try:
        content = resource_show(
            name=name, base_dir=_t.SKILLS_SRC_DIR, label="Skill", is_dir=True
        )
        typer.echo(content)
    except VaultSpecError as exc:
        _handle_error(exc)


@skills_app.command("edit")
def cmd_skills_edit(name: Annotated[str, typer.Argument(help="Skill name")]) -> None:
    """Open a skill in the configured editor."""
    from vaultspec_core.core import resource_edit
    from vaultspec_core.core import types as _t
    from vaultspec_core.core.exceptions import VaultSpecError

    try:
        resource_edit(name=name, base_dir=_t.SKILLS_SRC_DIR, label="Skill", is_dir=True)
    except VaultSpecError as exc:
        _handle_error(exc)


@skills_app.command("remove")
def cmd_skills_remove(
    name: Annotated[str, typer.Argument(help="Skill name")],
    force: Annotated[bool, typer.Option("--force", help="Skip confirmation")] = False,
) -> None:
    """Delete a skill."""
    from vaultspec_core.core import resource_remove
    from vaultspec_core.core import types as _t
    from vaultspec_core.core.exceptions import VaultSpecError

    try:
        resource_remove(
            name=name,
            base_dir=_t.SKILLS_SRC_DIR,
            label="Skill",
            force=force,
            is_dir=True,
            confirm_fn=typer.confirm,
        )
    except VaultSpecError as exc:
        _handle_error(exc)


@skills_app.command("rename")
def cmd_skills_rename(
    old_name: Annotated[str, typer.Argument(help="Current skill name")],
    new_name: Annotated[str, typer.Argument(help="New skill name")],
) -> None:
    """Rename an existing skill."""
    from vaultspec_core.core import resource_rename
    from vaultspec_core.core import types as _t
    from vaultspec_core.core.exceptions import VaultSpecError

    try:
        resource_rename(
            old_name=old_name,
            new_name=new_name,
            base_dir=_t.SKILLS_SRC_DIR,
            label="Skill",
            is_dir=True,
        )
    except VaultSpecError as exc:
        _handle_error(exc)


@skills_app.command("sync")
def cmd_skills_sync(
    prune: Annotated[bool, typer.Option("--prune", help="Remove stale files")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview changes")] = False,
) -> None:
    """Sync skills to tool destinations."""
    from vaultspec_core.console import get_console
    from vaultspec_core.core import skills_sync
    from vaultspec_core.core.sync import format_summary

    result = skills_sync(prune=prune, dry_run=dry_run)
    get_console().print(f"  [bold]{format_summary('Skills', result)}[/bold]")


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
    from rich import box
    from rich.table import Table

    from vaultspec_core.console import get_console
    from vaultspec_core.core import agents_list

    items = agents_list()
    console = get_console()
    if not items:
        console.print("No managed agents found.")
        return

    table = Table(box=box.SIMPLE_HEAD, highlight=False, show_edge=False)
    table.add_column("Name", no_wrap=True)
    table.add_column("Description", max_width=50, overflow="ellipsis")

    for item in items:
        table.add_row(item["name"], item["description"])

    console.print(table)


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
    from vaultspec_core.core.exceptions import VaultSpecError

    try:
        agents_add(name=name, description=description, force=force)
    except VaultSpecError as exc:
        _handle_error(exc)


@agents_app.command("show")
def cmd_agents_show(name: Annotated[str, typer.Argument(help="Agent name")]) -> None:
    """Display an agent's content."""
    from vaultspec_core.core import resource_show
    from vaultspec_core.core import types as _t
    from vaultspec_core.core.exceptions import VaultSpecError

    try:
        content = resource_show(name=name, base_dir=_t.AGENTS_SRC_DIR, label="Agent")
        typer.echo(content)
    except VaultSpecError as exc:
        _handle_error(exc)


@agents_app.command("edit")
def cmd_agents_edit(name: Annotated[str, typer.Argument(help="Agent name")]) -> None:
    """Open an agent in the configured editor."""
    from vaultspec_core.core import resource_edit
    from vaultspec_core.core import types as _t
    from vaultspec_core.core.exceptions import VaultSpecError

    try:
        resource_edit(name=name, base_dir=_t.AGENTS_SRC_DIR, label="Agent")
    except VaultSpecError as exc:
        _handle_error(exc)


@agents_app.command("remove")
def cmd_agents_remove(
    name: Annotated[str, typer.Argument(help="Agent name")],
    force: Annotated[bool, typer.Option("--force", help="Skip confirmation")] = False,
) -> None:
    """Delete an agent definition."""
    from vaultspec_core.core import resource_remove
    from vaultspec_core.core import types as _t
    from vaultspec_core.core.exceptions import VaultSpecError

    try:
        resource_remove(
            name=name,
            base_dir=_t.AGENTS_SRC_DIR,
            label="Agent",
            force=force,
            confirm_fn=typer.confirm,
        )
    except VaultSpecError as exc:
        _handle_error(exc)


@agents_app.command("rename")
def cmd_agents_rename(
    old_name: Annotated[str, typer.Argument(help="Current agent name")],
    new_name: Annotated[str, typer.Argument(help="New agent name")],
) -> None:
    """Rename an existing agent definition."""
    from vaultspec_core.core import resource_rename
    from vaultspec_core.core import types as _t
    from vaultspec_core.core.exceptions import VaultSpecError

    try:
        resource_rename(
            old_name=old_name,
            new_name=new_name,
            base_dir=_t.AGENTS_SRC_DIR,
            label="Agent",
        )
    except VaultSpecError as exc:
        _handle_error(exc)


@agents_app.command("sync")
def cmd_agents_sync(
    prune: Annotated[bool, typer.Option("--prune", help="Remove stale files")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview changes")] = False,
) -> None:
    """Sync agents to tool destinations."""
    from vaultspec_core.console import get_console
    from vaultspec_core.core import agents_sync
    from vaultspec_core.core.sync import format_summary

    result = agents_sync(prune=prune, dry_run=dry_run)
    get_console().print(f"  [bold]{format_summary('Agents', result)}[/bold]")


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
    from rich import box
    from rich.table import Table

    from vaultspec_core.console import get_console
    from vaultspec_core.core import system_show

    console = get_console()
    data = system_show()

    if not data["parts"]:
        console.print("[dim]No system parts found in .vaultspec/rules/system/[/dim]")
        return

    parts_table = Table(box=box.SIMPLE_HEAD, highlight=False, show_edge=False)
    parts_table.add_column("Name", no_wrap=True)
    parts_table.add_column("Tool Filter")
    parts_table.add_column("Lines", justify="right")

    for part in data["parts"]:
        parts_table.add_row(part["name"], part["tool_filter"], str(part["lines"]))

    console.print(parts_table)

    if data["targets"]:
        console.print()
        console.print("Generation targets:", style="bold")
        targets_table = Table(
            box=None, show_header=False, show_edge=False, padding=(0, 1)
        )
        targets_table.add_column("Tool")
        targets_table.add_column("Path")
        targets_table.add_column("Status", style="dim")
        for target in data["targets"]:
            targets_table.add_row(
                target["tool"], target["path"], f"[{target['managed']}]"
            )
        console.print(targets_table)


@system_app.command("sync")
def cmd_system_sync(
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview changes")] = False,
    force: Annotated[
        bool, typer.Option("--force", help="Overwrite non-managed files")
    ] = False,
) -> None:
    """Sync system prompts to tool destinations."""
    from vaultspec_core.console import get_console
    from vaultspec_core.core import system_sync
    from vaultspec_core.core.sync import format_summary

    result = system_sync(dry_run=dry_run, force=force)
    get_console().print(f"  [bold]{format_summary('System', result)}[/bold]")


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
    from rich import box
    from rich.table import Table

    from vaultspec_core.console import get_console
    from vaultspec_core.core.commands import hooks_list_data

    console = get_console()
    data = hooks_list_data()
    hooks = data["hooks"]

    if not hooks:
        console.print("No hooks defined.")
        console.print(
            f"  Add [dim].yaml[/dim] files to [bold]{data['hooks_dir']}/[/bold]"
        )
        console.print(
            "\n[dim]Supported events:[/dim] " + ", ".join(data["supported_events"])
        )
        return

    table = Table(box=box.SIMPLE_HEAD, highlight=False, show_edge=False)
    table.add_column("Name", no_wrap=True)
    table.add_column("Status")
    table.add_column("Event")
    table.add_column("Actions")

    for hook in hooks:
        if hook["enabled"]:
            status = "[bold green]enabled[/bold green]"
        else:
            status = "[dim]disabled[/dim]"
        table.add_row(hook["name"], status, hook["event"], hook["actions"])

    console.print(table)


@hooks_app.command("run")
def cmd_hooks_run(
    event: Annotated[str, typer.Argument(help="Event name")],
    path: Annotated[
        str | None, typer.Option("--path", help="Context path variable")
    ] = None,
) -> None:
    """Trigger hooks for a specific event."""
    from vaultspec_core.console import get_console
    from vaultspec_core.core.commands import hooks_run
    from vaultspec_core.core.exceptions import VaultSpecError

    try:
        results = hooks_run(event=event, path=path)
    except VaultSpecError as exc:
        _handle_error(exc)
        return

    console = get_console()
    if not results:
        console.print(f"[dim]No enabled hooks for event: {event}[/dim]")
        return

    for r in results:
        if r["success"]:
            icon = "[bold green]OK[/bold green]"
        else:
            icon = "[bold red]FAIL[/bold red]"
        console.print(f"  {r['hook_name']} ({r['action_type']}): {icon}")
        if r["output"]:
            for line in str(r["output"]).splitlines()[:5]:
                console.print(f"    {line}")
        if r["error"]:
            console.print(f"    [red]error:[/red] {r['error']}")

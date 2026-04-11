"""Spec command group  - manage framework resources in ``.vaultspec/``.

Sub-groups: ``spec rules`` (:data:`rules_app`), ``spec skills`` (:data:`skills_app`),
``spec agents`` (:data:`agents_app`), ``spec system`` (:data:`system_app`),
``spec hooks`` (:data:`hooks_app`), ``spec mcps`` (:data:`mcps_app`).
Delegates to :mod:`vaultspec_core.core`
CRUD functions via lazy imports to avoid circular-import issues. Mounted onto
:data:`.root.app` as the ``spec`` sub-group.
"""

import logging
from typing import Annotated

import typer

from vaultspec_core.cli._target import TargetOption, apply_target

logger = logging.getLogger(__name__)

spec_app = typer.Typer(
    help=(
        "Manage framework resources: rules, skills, agents, system prompts, and hooks."
    ),
    no_args_is_help=True,
)


def _handle_error(exc: Exception) -> None:
    """Convert a domain or OS exception to a CLI error exit."""
    from vaultspec_core.core.exceptions import VaultSpecError

    if isinstance(exc, VaultSpecError):
        typer.echo(f"Error: {exc}", err=True)
        if exc.hint:
            typer.echo(f"  Hint: {exc.hint}", err=True)
        raise typer.Exit(code=1) from exc
    if isinstance(exc, OSError):
        typer.echo(f"Error: {exc}", err=True)
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
def cmd_rules_list(
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    target: TargetOption = None,
) -> None:
    """List all available rules."""
    apply_target(target)
    from rich import box
    from rich.table import Table

    from vaultspec_core.console import get_console
    from vaultspec_core.core import rules_list

    items = rules_list()

    if json_output:
        import json

        typer.echo(json.dumps(items, indent=2, default=str))
        raise typer.Exit(0)

    table = Table(box=box.SIMPLE_HEAD, highlight=False, show_edge=False)
    table.add_column("Name", no_wrap=True)
    table.add_column("Source")

    for item in items:
        table.add_row(item["name"], item["source"])

    get_console().print(table)


@rules_app.command("add")
def cmd_rules_add(
    name: Annotated[str, typer.Option("--name", help="Rule name")],
    content: Annotated[
        str | None, typer.Option("--content", help="Rule content")
    ] = None,
    force: Annotated[bool, typer.Option("--force", help="Overwrite existing")] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    target: TargetOption = None,
) -> None:
    """Add a new custom rule."""
    apply_target(target)
    from vaultspec_core.core import rules_add
    from vaultspec_core.core.exceptions import VaultSpecError

    try:
        file_path = rules_add(name=name, content=content, force=force)
    except VaultSpecError as exc:
        _handle_error(exc)
        return

    if json_output:
        import json

        typer.echo(json.dumps({"path": str(file_path)}, indent=2))
        raise typer.Exit(0)


@rules_app.command("show")
def cmd_rules_show(
    name: Annotated[str, typer.Argument(help="Rule name")],
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    target: TargetOption = None,
) -> None:
    """Display a rule's content."""
    apply_target(target)
    from vaultspec_core.core import resource_show
    from vaultspec_core.core.exceptions import VaultSpecError
    from vaultspec_core.core.types import get_context

    try:
        content = resource_show(
            name=name, base_dir=get_context().rules_src_dir, label="Rule"
        )
        if json_output:
            import json

            typer.echo(json.dumps({"name": name, "content": content}, indent=2))
            raise typer.Exit(0)
        typer.echo(content)
    except (VaultSpecError, OSError) as exc:
        _handle_error(exc)


@rules_app.command("edit")
def cmd_rules_edit(
    name: Annotated[str, typer.Argument(help="Rule name")],
    target: TargetOption = None,
) -> None:
    """Open a rule in the configured editor."""
    apply_target(target)
    from vaultspec_core.core import resource_edit
    from vaultspec_core.core.exceptions import VaultSpecError
    from vaultspec_core.core.types import get_context

    try:
        resource_edit(name=name, base_dir=get_context().rules_src_dir, label="Rule")
    except VaultSpecError as exc:
        _handle_error(exc)


@rules_app.command("remove")
def cmd_rules_remove(
    name: Annotated[str, typer.Argument(help="Rule name")],
    force: Annotated[bool, typer.Option("--force", help="Skip confirmation")] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    target: TargetOption = None,
) -> None:
    """Delete a rule."""
    apply_target(target)
    from vaultspec_core.core import resource_remove
    from vaultspec_core.core.exceptions import VaultSpecError
    from vaultspec_core.core.types import get_context

    try:
        resource_remove(
            name=name,
            base_dir=get_context().rules_src_dir,
            label="Rule",
            force=force,
            confirm_fn=typer.confirm,
        )
    except (VaultSpecError, OSError) as exc:
        _handle_error(exc)
        return

    if json_output:
        import json

        typer.echo(json.dumps({"removed": name}, indent=2))
        raise typer.Exit(0)


@rules_app.command("rename")
def cmd_rules_rename(
    old_name: Annotated[str, typer.Argument(help="Current rule name")],
    new_name: Annotated[str, typer.Argument(help="New rule name")],
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    target: TargetOption = None,
) -> None:
    """Rename an existing rule."""
    apply_target(target)
    from vaultspec_core.core import resource_rename
    from vaultspec_core.core.exceptions import VaultSpecError
    from vaultspec_core.core.types import get_context

    try:
        new_path = resource_rename(
            old_name=old_name,
            new_name=new_name,
            base_dir=get_context().rules_src_dir,
            label="Rule",
        )
    except (VaultSpecError, OSError) as exc:
        _handle_error(exc)
        return

    if json_output:
        import json

        typer.echo(
            json.dumps(
                {"old_name": old_name, "new_name": new_name, "path": str(new_path)},
                indent=2,
            )
        )
        raise typer.Exit(0)


@rules_app.command("sync")
def cmd_rules_sync(
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview changes")] = False,
    force: Annotated[
        bool,
        typer.Option("--force", help="Prune stale files and overwrite user content"),
    ] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    target: TargetOption = None,
) -> None:
    """Sync rules to tool destinations."""
    apply_target(target)
    from vaultspec_core.console import get_console
    from vaultspec_core.core import rules_sync
    from vaultspec_core.core.sync import format_summary

    result = rules_sync(prune=force, dry_run=dry_run)

    if json_output:
        import dataclasses
        import json

        typer.echo(json.dumps(dataclasses.asdict(result), indent=2, default=str))
        raise typer.Exit(0)

    console = get_console()
    console.print(f"  [bold]{format_summary('Rules', result)}[/bold]")
    for warning in result.warnings:
        console.print(f"  [yellow]•[/yellow] {warning}")


@rules_app.command("revert")
def cmd_rules_revert(
    filename: Annotated[str, typer.Argument(help="Rule filename to revert")],
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    target: TargetOption = None,
) -> None:
    """Revert a rule to its snapshotted original."""
    apply_target(target)
    from vaultspec_core.core.revert import revert_resource
    from vaultspec_core.core.types import get_context

    vaultspec_dir = get_context().target_dir / ".vaultspec"
    if not filename.endswith(".md"):
        filename = f"{filename}.md"
    result = revert_resource(vaultspec_dir, "rules", filename)
    if result.get("reverted"):
        if json_output:
            import json

            typer.echo(json.dumps({"reverted": filename}, indent=2))
            raise typer.Exit(0)
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
def cmd_skills_list(
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    target: TargetOption = None,
) -> None:
    """List all available skills."""
    apply_target(target)
    from rich import box
    from rich.table import Table

    from vaultspec_core.console import get_console
    from vaultspec_core.core import skills_list

    items = skills_list()

    if json_output:
        import json

        typer.echo(json.dumps(items, indent=2, default=str))
        raise typer.Exit(0)

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
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    target: TargetOption = None,
) -> None:
    """Add a new skill."""
    apply_target(target)
    from vaultspec_core.core import skills_add
    from vaultspec_core.core.exceptions import VaultSpecError

    try:
        file_path = skills_add(
            name=name, description=description, force=force, template=template
        )
    except VaultSpecError as exc:
        _handle_error(exc)
        return

    if json_output:
        import json

        typer.echo(json.dumps({"path": str(file_path)}, indent=2))
        raise typer.Exit(0)


@skills_app.command("show")
def cmd_skills_show(
    name: Annotated[str, typer.Argument(help="Skill name")],
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    target: TargetOption = None,
) -> None:
    """Display a skill's content."""
    apply_target(target)
    from vaultspec_core.core import resource_show
    from vaultspec_core.core.exceptions import VaultSpecError
    from vaultspec_core.core.types import get_context

    try:
        content = resource_show(
            name=name, base_dir=get_context().skills_src_dir, label="Skill", is_dir=True
        )
        if json_output:
            import json

            typer.echo(json.dumps({"name": name, "content": content}, indent=2))
            raise typer.Exit(0)
        typer.echo(content)
    except (VaultSpecError, OSError) as exc:
        _handle_error(exc)


@skills_app.command("edit")
def cmd_skills_edit(
    name: Annotated[str, typer.Argument(help="Skill name")],
    target: TargetOption = None,
) -> None:
    """Open a skill in the configured editor."""
    apply_target(target)
    from vaultspec_core.core import resource_edit
    from vaultspec_core.core.exceptions import VaultSpecError
    from vaultspec_core.core.types import get_context

    try:
        resource_edit(
            name=name, base_dir=get_context().skills_src_dir, label="Skill", is_dir=True
        )
    except VaultSpecError as exc:
        _handle_error(exc)


@skills_app.command("remove")
def cmd_skills_remove(
    name: Annotated[str, typer.Argument(help="Skill name")],
    force: Annotated[bool, typer.Option("--force", help="Skip confirmation")] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    target: TargetOption = None,
) -> None:
    """Delete a skill."""
    apply_target(target)
    from vaultspec_core.core import resource_remove
    from vaultspec_core.core.exceptions import VaultSpecError
    from vaultspec_core.core.types import get_context

    try:
        resource_remove(
            name=name,
            base_dir=get_context().skills_src_dir,
            label="Skill",
            force=force,
            is_dir=True,
            confirm_fn=typer.confirm,
        )
    except (VaultSpecError, OSError) as exc:
        _handle_error(exc)
        return

    if json_output:
        import json

        typer.echo(json.dumps({"removed": name}, indent=2))
        raise typer.Exit(0)


@skills_app.command("rename")
def cmd_skills_rename(
    old_name: Annotated[str, typer.Argument(help="Current skill name")],
    new_name: Annotated[str, typer.Argument(help="New skill name")],
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    target: TargetOption = None,
) -> None:
    """Rename an existing skill."""
    apply_target(target)
    from vaultspec_core.core import resource_rename
    from vaultspec_core.core.exceptions import VaultSpecError
    from vaultspec_core.core.types import get_context

    try:
        new_path = resource_rename(
            old_name=old_name,
            new_name=new_name,
            base_dir=get_context().skills_src_dir,
            label="Skill",
            is_dir=True,
        )
    except (VaultSpecError, OSError) as exc:
        _handle_error(exc)
        return

    if json_output:
        import json

        typer.echo(
            json.dumps(
                {"old_name": old_name, "new_name": new_name, "path": str(new_path)},
                indent=2,
            )
        )
        raise typer.Exit(0)


@skills_app.command("sync")
def cmd_skills_sync(
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview changes")] = False,
    force: Annotated[
        bool,
        typer.Option("--force", help="Prune stale files and overwrite user content"),
    ] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    target: TargetOption = None,
) -> None:
    """Sync skills to tool destinations."""
    apply_target(target)
    from vaultspec_core.console import get_console
    from vaultspec_core.core import skills_sync
    from vaultspec_core.core.sync import format_summary

    result = skills_sync(prune=force, dry_run=dry_run)

    if json_output:
        import dataclasses
        import json

        typer.echo(json.dumps(dataclasses.asdict(result), indent=2, default=str))
        raise typer.Exit(0)

    console = get_console()
    console.print(f"  [bold]{format_summary('Skills', result)}[/bold]")
    for warning in result.warnings:
        console.print(f"  [yellow]•[/yellow] {warning}")


@skills_app.command("revert")
def cmd_skills_revert(
    filename: Annotated[str, typer.Argument(help="Skill filename to revert")],
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    target: TargetOption = None,
) -> None:
    """Revert a skill to its snapshotted original."""
    apply_target(target)
    from vaultspec_core.core.revert import revert_resource
    from vaultspec_core.core.types import get_context

    vaultspec_dir = get_context().target_dir / ".vaultspec"
    if not filename.endswith(".md"):
        filename = f"{filename}.md"
    result = revert_resource(vaultspec_dir, "skills", filename)
    if result.get("reverted"):
        if json_output:
            import json

            typer.echo(json.dumps({"reverted": filename}, indent=2))
            raise typer.Exit(0)
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
def cmd_agents_list(
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    target: TargetOption = None,
) -> None:
    """List all available agents."""
    apply_target(target)
    from rich import box
    from rich.table import Table

    from vaultspec_core.console import get_console
    from vaultspec_core.core import agents_list

    items = agents_list()

    if json_output:
        import json

        typer.echo(json.dumps(items, indent=2, default=str))
        raise typer.Exit(0)

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
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    target: TargetOption = None,
) -> None:
    """Add a new agent definition."""
    apply_target(target)
    from vaultspec_core.core import agents_add
    from vaultspec_core.core.exceptions import VaultSpecError

    try:
        file_path = agents_add(name=name, description=description, force=force)
    except VaultSpecError as exc:
        _handle_error(exc)
        return

    if json_output:
        import json

        typer.echo(json.dumps({"path": str(file_path)}, indent=2))
        raise typer.Exit(0)


@agents_app.command("show")
def cmd_agents_show(
    name: Annotated[str, typer.Argument(help="Agent name")],
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    target: TargetOption = None,
) -> None:
    """Display an agent's content."""
    apply_target(target)
    from vaultspec_core.core import resource_show
    from vaultspec_core.core.exceptions import VaultSpecError
    from vaultspec_core.core.types import get_context

    try:
        content = resource_show(
            name=name, base_dir=get_context().agents_src_dir, label="Agent"
        )
        if json_output:
            import json

            typer.echo(json.dumps({"name": name, "content": content}, indent=2))
            raise typer.Exit(0)
        typer.echo(content)
    except (VaultSpecError, OSError) as exc:
        _handle_error(exc)


@agents_app.command("edit")
def cmd_agents_edit(
    name: Annotated[str, typer.Argument(help="Agent name")],
    target: TargetOption = None,
) -> None:
    """Open an agent in the configured editor."""
    apply_target(target)
    from vaultspec_core.core import resource_edit
    from vaultspec_core.core.exceptions import VaultSpecError
    from vaultspec_core.core.types import get_context

    try:
        resource_edit(name=name, base_dir=get_context().agents_src_dir, label="Agent")
    except VaultSpecError as exc:
        _handle_error(exc)


@agents_app.command("remove")
def cmd_agents_remove(
    name: Annotated[str, typer.Argument(help="Agent name")],
    force: Annotated[bool, typer.Option("--force", help="Skip confirmation")] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    target: TargetOption = None,
) -> None:
    """Delete an agent definition."""
    apply_target(target)
    from vaultspec_core.core import resource_remove
    from vaultspec_core.core.exceptions import VaultSpecError
    from vaultspec_core.core.types import get_context

    try:
        resource_remove(
            name=name,
            base_dir=get_context().agents_src_dir,
            label="Agent",
            force=force,
            confirm_fn=typer.confirm,
        )
    except (VaultSpecError, OSError) as exc:
        _handle_error(exc)
        return

    if json_output:
        import json

        typer.echo(json.dumps({"removed": name}, indent=2))
        raise typer.Exit(0)


@agents_app.command("rename")
def cmd_agents_rename(
    old_name: Annotated[str, typer.Argument(help="Current agent name")],
    new_name: Annotated[str, typer.Argument(help="New agent name")],
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    target: TargetOption = None,
) -> None:
    """Rename an existing agent definition."""
    apply_target(target)
    from vaultspec_core.core import resource_rename
    from vaultspec_core.core.exceptions import VaultSpecError
    from vaultspec_core.core.types import get_context

    try:
        new_path = resource_rename(
            old_name=old_name,
            new_name=new_name,
            base_dir=get_context().agents_src_dir,
            label="Agent",
        )
    except (VaultSpecError, OSError) as exc:
        _handle_error(exc)
        return

    if json_output:
        import json

        typer.echo(
            json.dumps(
                {"old_name": old_name, "new_name": new_name, "path": str(new_path)},
                indent=2,
            )
        )
        raise typer.Exit(0)


@agents_app.command("sync")
def cmd_agents_sync(
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview changes")] = False,
    force: Annotated[
        bool,
        typer.Option("--force", help="Prune stale files and overwrite user content"),
    ] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    target: TargetOption = None,
) -> None:
    """Sync agents to tool destinations."""
    apply_target(target)
    from vaultspec_core.console import get_console
    from vaultspec_core.core import agents_sync
    from vaultspec_core.core.sync import format_summary

    result = agents_sync(prune=force, dry_run=dry_run)

    if json_output:
        import dataclasses
        import json

        typer.echo(json.dumps(dataclasses.asdict(result), indent=2, default=str))
        raise typer.Exit(0)

    console = get_console()
    console.print(f"  [bold]{format_summary('Agents', result)}[/bold]")
    for warning in result.warnings:
        console.print(f"  [yellow]•[/yellow] {warning}")


@agents_app.command("revert")
def cmd_agents_revert(
    filename: Annotated[str, typer.Argument(help="Agent filename to revert")],
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    target: TargetOption = None,
) -> None:
    """Revert an agent to its snapshotted original."""
    apply_target(target)
    from vaultspec_core.core.revert import revert_resource
    from vaultspec_core.core.types import get_context

    vaultspec_dir = get_context().target_dir / ".vaultspec"
    if not filename.endswith(".md"):
        filename = f"{filename}.md"
    result = revert_resource(vaultspec_dir, "agents", filename)
    if result.get("reverted"):
        if json_output:
            import json

            typer.echo(json.dumps({"reverted": filename}, indent=2))
            raise typer.Exit(0)
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
def cmd_system_show(
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    target: TargetOption = None,
) -> None:
    """Display system prompt parts and targets."""
    apply_target(target)
    from rich import box
    from rich.table import Table

    from vaultspec_core.console import get_console
    from vaultspec_core.core import system_show

    data = system_show()

    if json_output:
        import json

        typer.echo(json.dumps(data, indent=2, default=str))
        raise typer.Exit(0)

    console = get_console()

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
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    target: TargetOption = None,
) -> None:
    """Sync system prompts to tool destinations."""
    apply_target(target)
    from vaultspec_core.console import get_console
    from vaultspec_core.core import system_sync
    from vaultspec_core.core.sync import format_summary

    result = system_sync(dry_run=dry_run, force=force)

    if json_output:
        import dataclasses
        import json

        typer.echo(json.dumps(dataclasses.asdict(result), indent=2, default=str))
        raise typer.Exit(0)

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
def cmd_hooks_list(
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    target: TargetOption = None,
) -> None:
    """List all defined hooks."""
    apply_target(target)
    from rich import box
    from rich.table import Table

    from vaultspec_core.console import get_console
    from vaultspec_core.core.commands import hooks_list_data

    data = hooks_list_data()

    if json_output:
        import json

        typer.echo(json.dumps(data, indent=2, default=str))
        raise typer.Exit(0)

    console = get_console()
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
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    target: TargetOption = None,
) -> None:
    """Trigger hooks for a specific event."""
    apply_target(target)
    from vaultspec_core.console import get_console
    from vaultspec_core.core.commands import hooks_run
    from vaultspec_core.core.exceptions import VaultSpecError

    try:
        results = hooks_run(event=event, path=path)
    except VaultSpecError as exc:
        _handle_error(exc)
        return

    if json_output:
        import json

        typer.echo(json.dumps(results, indent=2, default=str))
        raise typer.Exit(0)

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


# =============================================================================
# MCPs
# =============================================================================

mcps_app = typer.Typer(
    help="Manage MCP server definitions and synced .mcp.json entries.",
    no_args_is_help=True,
)
spec_app.add_typer(mcps_app, name="mcps")


@mcps_app.command("list")
def cmd_mcps_list(
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    target: TargetOption = None,
) -> None:
    """List all registered MCP server definitions."""
    apply_target(target)
    from rich import box
    from rich.table import Table

    from vaultspec_core.console import get_console
    from vaultspec_core.core import mcp_list

    items = mcp_list()

    if json_output:
        import json

        typer.echo(json.dumps(items, indent=2, default=str))
        raise typer.Exit(0)

    console = get_console()
    if not items:
        console.print("No MCP server definitions found.")
        return

    table = Table(box=box.SIMPLE_HEAD, highlight=False, show_edge=False)
    table.add_column("Name", no_wrap=True)
    table.add_column("Source")

    for item in items:
        table.add_row(item["name"], item["source"])

    console.print(table)


@mcps_app.command("add")
def cmd_mcps_add(
    name: Annotated[str, typer.Option("--name", help="MCP server name")],
    config: Annotated[
        str | None, typer.Option("--config", help="Server config as JSON string")
    ] = None,
    force: Annotated[bool, typer.Option("--force", help="Overwrite existing")] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    target: TargetOption = None,
) -> None:
    """Add a new custom MCP server definition."""
    apply_target(target)
    import json as json_mod

    from vaultspec_core.core import mcp_add
    from vaultspec_core.core.exceptions import VaultSpecError

    parsed_config = None
    if config is not None:
        try:
            parsed_config = json_mod.loads(config)
        except json_mod.JSONDecodeError as exc:
            typer.echo(f"Error: Invalid JSON config: {exc}", err=True)
            raise typer.Exit(code=1) from exc

    try:
        file_path = mcp_add(name=name, config=parsed_config, force=force)
    except VaultSpecError as exc:
        _handle_error(exc)
        return

    if json_output:
        import json

        typer.echo(json.dumps({"path": str(file_path)}, indent=2))
        raise typer.Exit(0)


@mcps_app.command("remove")
def cmd_mcps_remove(
    name: Annotated[str, typer.Argument(help="MCP server name")],
    force: Annotated[bool, typer.Option("--force", help="Skip confirmation")] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    target: TargetOption = None,
) -> None:
    """Remove an MCP server definition."""
    apply_target(target)
    from vaultspec_core.core import mcp_remove
    from vaultspec_core.core.exceptions import VaultSpecError

    if not force and not typer.confirm(f"Remove MCP definition '{name}'?"):
        raise typer.Abort()

    try:
        mcp_remove(name=name)
    except VaultSpecError as exc:
        _handle_error(exc)
        return

    if json_output:
        import json

        typer.echo(json.dumps({"removed": name}, indent=2))
        raise typer.Exit(0)


@mcps_app.command("sync")
def cmd_mcps_sync(
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview changes")] = False,
    force: Annotated[
        bool,
        typer.Option("--force", help="Overwrite modified entries"),
    ] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    target: TargetOption = None,
) -> None:
    """Sync MCP definitions to .mcp.json."""
    apply_target(target)
    from vaultspec_core.console import get_console
    from vaultspec_core.core import mcp_sync
    from vaultspec_core.core.sync import format_summary

    result = mcp_sync(force=force, dry_run=dry_run)

    if json_output:
        import dataclasses
        import json

        typer.echo(json.dumps(dataclasses.asdict(result), indent=2, default=str))
        raise typer.Exit(0)

    console = get_console()
    console.print(f"  [bold]{format_summary('MCPs', result)}[/bold]")
    for warning in result.warnings:
        console.print(f"  [yellow]•[/yellow] {warning}")

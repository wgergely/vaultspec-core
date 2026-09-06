"""``vaultspec-core spec skills`` - manage workflow skills.

Defines :data:`skills_app`, mounted by :mod:`vaultspec_core.cli.spec_cmd`
onto :data:`~vaultspec_core.cli.spec_cmd_app.spec_app` as the ``skills``
command group. Delegates to :mod:`vaultspec_core.core` CRUD functions via
lazy imports to avoid circular-import issues.
"""

from pathlib import Path
from typing import Annotated

import typer

from vaultspec_core.cli._app import make_app
from vaultspec_core.cli._errors import handle_error as _handle_error
from vaultspec_core.cli._target import TargetOption, apply_target
from vaultspec_core.cli.spec_cmd_shared import (
    apply_provider_filter,
    emit_json,
    emit_sync_result,
    print_complete_sync_notice,
    print_source_mutation_notice,
    restore_resource_command,
    run_edit_command,
    spec_status_command,
)

skills_app = make_app(
    help="Manage workflow skills and synced skill outputs",
    no_args_is_help=True,
)


@skills_app.command("list")
def cmd_skills_list(
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    target: TargetOption = None,
) -> None:
    """List all available skills."""
    apply_target(target)
    from vaultspec_core.core import skills_list

    items = skills_list()

    if json_output:
        emit_json("spec.skills.list", "unchanged", {"items": items})
        raise typer.Exit(0)

    from vaultspec_core.cli.rendering import (
        Column,
        render_listing,
        summary_line,
        truncate,
    )

    rows = [
        {"name": item["name"], "description": truncate(item["description"], 60)}
        for item in items
    ]
    render_listing(
        rows,
        [Column("name"), Column("description")],
        title="skills",
        summary=summary_line(len(rows), "skills"),
        empty="no skills",
    )


@skills_app.command("add")
def cmd_skills_add(
    name: Annotated[str, typer.Argument(help="Skill name")],
    description: Annotated[
        str, typer.Option("--description", help="Skill description")
    ] = "",
    body: Annotated[
        str | None, typer.Option("--body", help="Skill body content")
    ] = None,
    from_file: Annotated[
        Path | None, typer.Option("--from-file", help="Read body content from file")
    ] = None,
    force: Annotated[bool, typer.Option("--force", help="Overwrite existing")] = False,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Preview without writing")
    ] = False,
    template: Annotated[
        str | None, typer.Option("--template", help="Template to use")
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    target: TargetOption = None,
) -> None:
    """Add a new skill."""
    apply_target(target)

    if from_file and body is not None:
        typer.echo("Error: Cannot specify both --body and --from-file.", err=True)
        raise typer.Exit(code=1)

    resolved_body = None
    if from_file:
        if not from_file.exists():
            typer.echo(f"Error: File not found: {from_file}", err=True)
            raise typer.Exit(code=1)
        resolved_body = from_file.read_text(encoding="utf-8")
    elif body is not None:
        resolved_body = body

    from vaultspec_core.core import skills_add
    from vaultspec_core.core.exceptions import VaultSpecError

    try:
        file_path = skills_add(
            name=name,
            description=description,
            force=force,
            template=template,
            body=resolved_body,
            dry_run=dry_run,
        )
    except VaultSpecError as exc:
        _handle_error(exc, json_output=json_output)
        return

    if json_output:
        emit_json("spec.skills.add", "created", {"path": str(file_path)})
        raise typer.Exit(0)

    action = "Would create skill source" if dry_run else "Skill source updated"
    print_source_mutation_notice(file_path, action=action)


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
            emit_json(
                "spec.skills.show", "unchanged", {"name": name, "content": content}
            )
            raise typer.Exit(0)
        typer.echo(content)
    except (VaultSpecError, OSError) as exc:
        _handle_error(exc, json_output=json_output)


@skills_app.command("edit")
def cmd_skills_edit(
    name: Annotated[str, typer.Argument(help="Skill name")],
    editor: Annotated[
        str | None,
        typer.Option(
            "--editor",
            help=(
                "Override the editor for this invocation. Must name a known "
                "editor program; arguments are allowed (e.g. 'code --wait'). "
                "For an editor outside that set, use VAULTSPEC_EDITOR."
            ),
        ),
    ] = None,
    target: TargetOption = None,
) -> None:
    """Open a skill in the configured editor.

    Editor resolution order:
      1. Command-line --editor flag
      2. Project-local config (vaultspec-core config set editor <value>)
      3. $VISUAL environment variable
      4. $EDITOR environment variable
      5. Fallback to 'vi'

    If no working editor is resolved, the command exits with code 2.
    """
    apply_target(target)
    from vaultspec_core.core.types import get_context

    run_edit_command(
        name=name,
        base_dir=get_context().skills_src_dir,
        label="Skill",
        is_dir=True,
        editor=editor,
    )


@skills_app.command("remove")
def cmd_skills_remove(
    name: Annotated[str, typer.Argument(help="Skill name")],
    force: Annotated[
        bool,
        typer.Option(
            "--yes",
            "-y",
            "--force",
            help="Confirm removal without prompting",
        ),
    ] = False,
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
        _handle_error(exc, json_output=json_output)
        return

    if json_output:
        emit_json("spec.skills.remove", "removed", {"removed": name})
        raise typer.Exit(0)

    print_source_mutation_notice(
        get_context().skills_src_dir / name,
        action="Skill source removed",
    )


@skills_app.command("rename")
def cmd_skills_rename(
    old_name: Annotated[str, typer.Argument(help="Current skill name")],
    new_name: Annotated[str, typer.Argument(help="New skill name")],
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    target: TargetOption = None,
) -> None:
    """Rename an existing skill atomically.

    Rewrites both directory name and SKILL.md frontmatter name.
    """
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
        _handle_error(exc, json_output=json_output)
        return

    if json_output:
        emit_json(
            "spec.skills.rename",
            "updated",
            {"old_name": old_name, "new_name": new_name, "path": str(new_path)},
        )
        raise typer.Exit(0)

    print_source_mutation_notice(new_path, action="Skill source renamed")


@skills_app.command("sync")
def cmd_skills_sync(
    provider: Annotated[
        str,
        typer.Argument(
            help="Provider to sync (all, claude, gemini, antigravity, codex)"
        ),
    ] = "all",
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview changes")] = False,
    force: Annotated[
        bool,
        typer.Option("--force", help="Prune stale files and overwrite user content"),
    ] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    target: TargetOption = None,
) -> None:
    """Sync only skill files; use vaultspec-core sync for complete refresh."""
    apply_target(target)
    apply_provider_filter(provider)
    from vaultspec_core.core import skills_sync

    result = skills_sync(prune=force, dry_run=dry_run)

    if not json_output:
        print_complete_sync_notice(resource="skill")
    emit_sync_result(result, label="Skills", dry_run=dry_run, json_output=json_output)


@skills_app.command("restore")
def cmd_skills_restore(
    filename: Annotated[str, typer.Argument(help="Skill name or filename to restore")],
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    target: TargetOption = None,
) -> None:
    """Restore a skill to its snapshotted original."""
    apply_target(target)
    restore_resource_command(
        category="skills", label="skill", filename=filename, json_output=json_output
    )


@skills_app.command("status")
def cmd_skills_status(
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    target: TargetOption = None,
) -> None:
    """Report skills sync status against provider destinations."""
    apply_target(target)
    from vaultspec_core.core import skills_sync

    result = skills_sync(prune=True, dry_run=True)
    spec_status_command(result, label="Skills", json_output=json_output)

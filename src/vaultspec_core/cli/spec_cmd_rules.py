"""``vaultspec-core spec rules`` - manage framework rule sources.

Defines :data:`rules_app`, mounted by :mod:`vaultspec_core.cli.spec_cmd`
onto :data:`~vaultspec_core.cli.spec_cmd_app.spec_app` as the ``rules``
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
    resource_path,
    restore_resource_command,
    run_edit_command,
    spec_status_command,
)

rules_app = make_app(
    help="Manage framework rule sources and synced rule outputs",
    no_args_is_help=True,
)


@rules_app.command("list")
def cmd_rules_list(
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    target: TargetOption = None,
) -> None:
    """List all available rules."""
    apply_target(target)
    from vaultspec_core.core import rules_list

    items = rules_list()

    if json_output:
        emit_json("spec.rules.list", "unchanged", {"items": items})
        raise typer.Exit(0)

    from vaultspec_core.cli.rendering import Column, render_listing, summary_line

    rows = [{"name": item["name"], "source": item["source"]} for item in items]
    render_listing(
        rows,
        [Column("name"), Column("source")],
        title="rules",
        summary=summary_line(len(rows), "rules"),
        empty="no rules",
    )


@rules_app.command("add")
def cmd_rules_add(
    name: Annotated[str, typer.Argument(help="Rule name")],
    body: Annotated[
        str | None, typer.Option("--body", help="Rule body content")
    ] = None,
    from_file: Annotated[
        Path | None, typer.Option("--from-file", help="Read body content from file")
    ] = None,
    force: Annotated[bool, typer.Option("--force", help="Overwrite existing")] = False,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Preview without writing")
    ] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    target: TargetOption = None,
) -> None:
    """Add a new custom rule source under .vaultspec/."""
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

    from vaultspec_core.core import rules_add
    from vaultspec_core.core.exceptions import VaultSpecError

    try:
        file_path = rules_add(
            name=name, content=resolved_body, force=force, dry_run=dry_run
        )
    except VaultSpecError as exc:
        _handle_error(exc, json_output=json_output)
        return

    if json_output:
        emit_json("spec.rules.add", "created", {"path": str(file_path)})
        raise typer.Exit(0)

    action = "Would create rule source" if dry_run else "Rule source updated"
    print_source_mutation_notice(file_path, action=action)


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
            emit_json(
                "spec.rules.show", "unchanged", {"name": name, "content": content}
            )
            raise typer.Exit(0)
        typer.echo(content)
    except (VaultSpecError, OSError) as exc:
        _handle_error(exc, json_output=json_output)


@rules_app.command("edit")
def cmd_rules_edit(
    name: Annotated[str, typer.Argument(help="Rule name")],
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
    """Open a rule in the configured editor.

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
        base_dir=get_context().rules_src_dir,
        label="Rule",
        is_dir=False,
        editor=editor,
    )


@rules_app.command("remove")
def cmd_rules_remove(
    name: Annotated[str, typer.Argument(help="Rule name")],
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
        _handle_error(exc, json_output=json_output)
        return

    if json_output:
        emit_json("spec.rules.remove", "removed", {"removed": name})
        raise typer.Exit(0)

    print_source_mutation_notice(
        resource_path(get_context().rules_src_dir, name),
        action="Rule source removed",
    )


@rules_app.command("rename")
def cmd_rules_rename(
    old_name: Annotated[str, typer.Argument(help="Current rule name")],
    new_name: Annotated[str, typer.Argument(help="New rule name")],
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    target: TargetOption = None,
) -> None:
    """Rename an existing rule atomically.

    Rewrites both filename and frontmatter name.
    """
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
        _handle_error(exc, json_output=json_output)
        return

    if json_output:
        emit_json(
            "spec.rules.rename",
            "updated",
            {"old_name": old_name, "new_name": new_name, "path": str(new_path)},
        )
        raise typer.Exit(0)

    print_source_mutation_notice(new_path, action="Rule source renamed")


@rules_app.command("sync")
def cmd_rules_sync(
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
    """Sync only rule files; use vaultspec-core sync for complete refresh."""
    apply_target(target)
    apply_provider_filter(provider)
    from vaultspec_core.core import rules_sync

    result = rules_sync(prune=force, dry_run=dry_run)

    if not json_output:
        print_complete_sync_notice(resource="rule")
    emit_sync_result(result, label="Rules", dry_run=dry_run, json_output=json_output)


@rules_app.command("restore")
def cmd_rules_restore(
    filename: Annotated[str, typer.Argument(help="Rule name or filename to restore")],
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    target: TargetOption = None,
) -> None:
    """Restore a rule to its snapshotted original."""
    apply_target(target)
    restore_resource_command(
        category="rules", label="rule", filename=filename, json_output=json_output
    )


@rules_app.command("status")
def cmd_rules_status(
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    target: TargetOption = None,
) -> None:
    """Report rules sync status against provider destinations."""
    apply_target(target)
    from vaultspec_core.core import rules_sync

    result = rules_sync(prune=True, dry_run=True)
    spec_status_command(result, label="Rules", json_output=json_output)

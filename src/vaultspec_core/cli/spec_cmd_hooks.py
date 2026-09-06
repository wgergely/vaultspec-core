"""``vaultspec-core spec hooks`` - list and run declarative workspace hooks.

Defines :data:`hooks_app` and also hosts the ``vaultspec-core spec
precommit`` sub-group (:data:`precommit_app`), which manages the prek
pre-commit hook boundary, and the ``spec gitignore`` and ``spec
gitattributes`` sub-groups (:data:`gitignore_app`, :data:`gitattributes_app`),
which record whether vaultspec maintains its managed block in each of those
files. All four are mounted by
:mod:`vaultspec_core.cli.spec_cmd` onto
:data:`~vaultspec_core.cli.spec_cmd_app.spec_app`. Delegates to
:mod:`vaultspec_core.core` CRUD functions via lazy imports to avoid
circular-import issues.
"""

from dataclasses import replace
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
)

# =============================================================================
# Hooks
# =============================================================================

hooks_app = make_app(
    help="List and run shell-based workspace hooks",
    no_args_is_help=True,
)


@hooks_app.command("list")
def cmd_hooks_list(
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    target: TargetOption = None,
) -> None:
    """List all defined hooks."""
    apply_target(target)
    from vaultspec_core.core.commands import hooks_list_data

    data = hooks_list_data()

    if json_output:
        emit_json("spec.hooks.list", "unchanged", data)
        raise typer.Exit(0)

    from vaultspec_core.cli.rendering import Cell, Column, render_listing, summary_line
    from vaultspec_core.console import get_console

    hooks = data["hooks"]
    console = get_console()

    if not hooks:
        console.print("No hooks defined.")
        console.print(
            f"  Add [dim].yaml[/dim] files to [bold]{data['hooks_dir']}/[/bold]"
        )
        console.print(
            "\n[dim]Supported events:[/dim] " + ", ".join(data["supported_events"])
        )
        return

    rows = [
        {
            "name": hook["name"],
            "status": Cell("enabled", style="bold green")
            if hook["enabled"]
            else Cell("disabled", style="dim"),
            "trust": Cell("trusted", style="bold green")
            if hook["trusted"]
            else Cell("untrusted", style="yellow"),
            "event": hook["event"],
            "actions": hook["actions"],
        }
        for hook in hooks
    ]
    render_listing(
        rows,
        [
            Column("name"),
            Column("status"),
            Column("trust"),
            Column("event"),
            Column("actions"),
        ],
        title="hooks",
        summary=summary_line(len(rows), "hooks"),
        empty="no hooks",
    )
    if any(not hook["trusted"] for hook in hooks):
        console.print(
            "\n[dim]Untrusted hooks are never run. Their commands would "
            "execute as you, and a repository cannot approve its own; review "
            "them, then run[/dim] [bold]vaultspec-core spec hooks trust[/bold]."
        )


@hooks_app.command("add")
def cmd_hooks_add(
    name: Annotated[str, typer.Argument(help="Hook name")],
    event: Annotated[
        str, typer.Option("--event", help="Lifecycle event to trigger on")
    ] = "vault.document.created",
    command: Annotated[str, typer.Option("--command", help="Command to run")] = "",
    body: Annotated[
        str | None, typer.Option("--body", help="Hook body content")
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
    """Add a new declarative hook under .vaultspec/."""
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

    from vaultspec_core.core import hooks_add
    from vaultspec_core.core.exceptions import VaultSpecError

    try:
        file_path = hooks_add(
            name=name,
            event=event,
            command=command,
            force=force,
            body=resolved_body,
            dry_run=dry_run,
        )
    except VaultSpecError as exc:
        _handle_error(exc, json_output=json_output)
        return

    if json_output:
        emit_json("spec.hooks.add", "created", {"path": str(file_path)})
        raise typer.Exit(0)

    action = "Would create hook source" if dry_run else "Hook source updated"
    print_source_mutation_notice(file_path, action=action)


@hooks_app.command("show")
def cmd_hooks_show(
    name: Annotated[str, typer.Argument(help="Hook name")],
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    target: TargetOption = None,
) -> None:
    """Display a hook's content."""
    apply_target(target)
    from vaultspec_core.core import hooks_show
    from vaultspec_core.core.exceptions import VaultSpecError

    try:
        content = hooks_show(name=name)
        if json_output:
            emit_json(
                "spec.hooks.show", "unchanged", {"name": name, "content": content}
            )
            raise typer.Exit(0)
        typer.echo(content)
    except (VaultSpecError, OSError) as exc:
        _handle_error(exc, json_output=json_output)


@hooks_app.command("edit")
def cmd_hooks_edit(
    name: Annotated[str, typer.Argument(help="Hook name")],
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
    """Open a hook in the configured editor."""
    apply_target(target)
    from vaultspec_core.core import hooks_edit
    from vaultspec_core.core.exceptions import (
        EditorCancellationError,
        EditorResolutionError,
        EditorSubprocessError,
        VaultSpecError,
    )

    try:
        hooks_edit(name=name, editor=editor)
    except EditorResolutionError as exc:
        typer.echo(f"Error: {exc}", err=True)
        if exc.hint:
            typer.echo(f"  Hint: {exc.hint}", err=True)
        raise typer.Exit(code=2) from exc
    except EditorSubprocessError as exc:
        typer.echo(f"Error: {exc}", err=True)
        if exc.hint:
            typer.echo(f"  Hint: {exc.hint}", err=True)
        raise typer.Exit(code=3) from exc
    except EditorCancellationError as exc:
        typer.echo(f"Error: {exc}", err=True)
        if exc.hint:
            typer.echo(f"  Hint: {exc.hint}", err=True)
        raise typer.Exit(code=4) from exc
    except VaultSpecError as exc:
        _handle_error(exc)
    except OSError as exc:
        _handle_error(exc)


@hooks_app.command("rename")
def cmd_hooks_rename(
    old_name: Annotated[str, typer.Argument(help="Current hook name")],
    new_name: Annotated[str, typer.Argument(help="New hook name")],
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    target: TargetOption = None,
) -> None:
    """Rename an existing hook atomically."""
    apply_target(target)
    from vaultspec_core.core import hooks_rename
    from vaultspec_core.core.exceptions import VaultSpecError

    try:
        new_path = hooks_rename(old_name=old_name, new_name=new_name)
    except (VaultSpecError, OSError) as exc:
        _handle_error(exc, json_output=json_output)
        return

    if json_output:
        emit_json(
            "spec.hooks.rename",
            "updated",
            {"old_name": old_name, "new_name": new_name, "path": str(new_path)},
        )
        raise typer.Exit(0)

    print_source_mutation_notice(new_path, action="Hook source renamed")


@hooks_app.command("remove")
def cmd_hooks_remove(
    name: Annotated[str, typer.Argument(help="Hook name")],
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
    """Delete a hook."""
    apply_target(target)
    from vaultspec_core.core import hooks_remove
    from vaultspec_core.core.exceptions import VaultSpecError

    try:
        hooks_remove(
            name=name,
            force=force,
            confirm_fn=typer.confirm,
        )
    except (VaultSpecError, OSError) as exc:
        _handle_error(exc, json_output=json_output)
        return

    if json_output:
        emit_json("spec.hooks.remove", "removed", {"removed": name})
        raise typer.Exit(0)

    from vaultspec_core.core.hooks import resolve_hook_path

    print_source_mutation_notice(
        resolve_hook_path(name),
        action="Hook source removed",
    )


@hooks_app.command("restore")
def cmd_hooks_restore(
    filename: Annotated[str, typer.Argument(help="Hook name or filename to restore")],
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    target: TargetOption = None,
) -> None:
    """Restore a hook to its snapshotted original (not supported for custom hooks)."""
    apply_target(target)
    _ = filename
    if json_output:
        emit_json(
            "spec.hooks.restore",
            "failed",
            {"message": "Custom hooks cannot be restored"},
        )
        raise typer.Exit(1)
    typer.echo("Error: Custom hooks cannot be restored.", err=True)
    raise typer.Exit(code=1)


@hooks_app.command("sync")
def cmd_hooks_sync(
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
    """Sync only hooks files; use vaultspec-core sync for complete refresh."""
    apply_target(target)
    apply_provider_filter(provider)
    from vaultspec_core.core import hooks_sync

    result = hooks_sync(prune=force, dry_run=dry_run)

    if not json_output:
        print_complete_sync_notice(resource="hook")
    emit_sync_result(result, label="Hooks", dry_run=dry_run, json_output=json_output)


@hooks_app.command("status")
def cmd_hooks_status(
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    target: TargetOption = None,
) -> None:
    """Report declarative hooks parsing and taxonomy compliance status."""
    apply_target(target)
    from vaultspec_core.core import hooks_status

    status = hooks_status()

    if json_output:
        emit_json("spec.hooks.status", status["status"], status)
        raise typer.Exit(0 if status["status"] == "ok" else 1)

    from vaultspec_core.cli.rendering import Field, render_record
    from vaultspec_core.console import get_console

    status_str = str(status["status"])
    status_style = (
        "green" if status_str == "ok" else ("yellow" if status_str == "warn" else "red")
    )
    fields = [
        Field("status", status_str, style=status_style),
        Field("hooks_dir", str(status["hooks_dir"])),
        Field("definitions", ", ".join(status["definitions"]) or "none"),
    ]
    render_record(fields, title="hooks status")

    console = get_console()
    for warning in status["warnings"]:
        console.print(f"  [yellow]-[/yellow] {warning}")
    for error in status["errors"]:
        console.print(f"  [red]-[/red] {error}")
    if status["status"] != "ok":
        raise typer.Exit(code=1)


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
    from vaultspec_core.cli._hook_trust import consent_gate
    from vaultspec_core.console import get_console
    from vaultspec_core.core.commands import hooks_run
    from vaultspec_core.core.exceptions import VaultSpecError

    consent_gate(event, json_output=json_output)

    try:
        results = hooks_run(event=event, path=path)
    except VaultSpecError as exc:
        _handle_error(exc, json_output=json_output)
        return

    if json_output:
        emit_json("spec.hooks.run", "unchanged", {"results": results})
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


@hooks_app.command("trust")
def cmd_hooks_trust(
    name: Annotated[
        str | None,
        typer.Argument(help="Hook name; omit to cover every hook in the workspace"),
    ] = None,
    revoke: Annotated[
        bool,
        typer.Option("--revoke", help="Withdraw approval for this workspace's hooks"),
    ] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    target: TargetOption = None,
) -> None:
    """Approve this workspace's hooks to run their shell commands as you.

    Hook files are shared through git, so a checkout arrives carrying commands
    its author chose. Approval is therefore recorded on this machine rather than
    in the workspace, and is pinned to each file's current contents: editing an
    approved hook, or pulling a change to one, withdraws the approval until you
    run this again. Use --revoke to withdraw it yourself.
    """
    apply_target(target)
    from vaultspec_core.cli._hook_trust import describe_hook
    from vaultspec_core.core.exceptions import ResourceNotFoundError
    from vaultspec_core.core.types import get_context
    from vaultspec_core.hooks import grant, load_hooks
    from vaultspec_core.hooks import revoke as revoke_trust

    ctx = get_context()

    if revoke:
        dropped = revoke_trust(ctx.hooks_dir)
        if json_output:
            emit_json("spec.hooks.trust", "removed", {"revoked": dropped})
            raise typer.Exit(0)
        from vaultspec_core.console import get_console

        get_console().print(f"Withdrew approval for {dropped} hook(s).")
        return

    hooks = load_hooks(ctx.hooks_dir)
    if name is not None:
        hooks = [hook for hook in hooks if hook.name == name]
        if not hooks:
            _handle_error(
                ResourceNotFoundError(f"Hook '{name}' not found."),
                json_output=json_output,
            )
            return

    paths = [hook.source_path for hook in hooks if hook.source_path is not None]
    recorded = grant(paths)
    approved = sorted(path.name for path in recorded)

    if json_output:
        emit_json("spec.hooks.trust", "updated", {"trusted": approved})
        raise typer.Exit(0)

    from vaultspec_core.console import get_console

    console = get_console()
    if not approved:
        console.print("No hooks to approve.")
        return
    console.print(f"Approved {len(approved)} hook(s) in {ctx.hooks_dir}:")
    # Echo the commands that were just approved rather than only the filenames.
    # This verb is the one place an operator commits to running them, so it is
    # the one place the record of what they agreed to has to be legible.
    for hook in hooks:
        if hook.source_path is None or hook.source_path not in recorded:
            continue
        for line in describe_hook(hook, ctx.target_dir):
            console.print(line, highlight=False)
    console.print(
        "[dim]Approval is recorded on this machine and pinned to each file's "
        "contents; editing a hook asks again.[/dim]"
    )


# =============================================================================
# Pre-commit boundary (prek)
# =============================================================================

precommit_app = make_app(
    help="Manage whether and where vaultspec's pre-commit hooks are scaffolded.",
    no_args_is_help=True,
)
gitignore_app = make_app(
    help="Manage whether vaultspec maintains its block in .gitignore.",
    no_args_is_help=True,
)

gitattributes_app = make_app(
    help="Manage whether vaultspec maintains its block in .gitattributes.",
    no_args_is_help=True,
)


def _set_precommit_policy(
    *, enabled: bool, json_output: bool, target: Path | None
) -> None:
    """Persist the workspace's pre-commit policy and report the outcome.

    The one implementation behind ``enable`` and ``disable``, which differ only
    by the boolean they persist and the sentence they print. Both are idempotent
    and report an already-satisfied request as success, so a sync script can set
    the policy unconditionally.
    """
    apply_target(target)
    from vaultspec_core.core.exceptions import VaultSpecError
    from vaultspec_core.core.types import get_context
    from vaultspec_core.core.workspace_mode import (
        HooksDeclaration,
        read_hooks_declaration,
        write_hooks_declaration,
    )

    root = get_context().target_dir
    try:
        already = read_hooks_declaration(root).pre_commit == enabled
        if not already:
            write_hooks_declaration(root, HooksDeclaration(pre_commit=enabled))
    except (VaultSpecError, OSError) as exc:
        _handle_error(exc, json_output=json_output)
        return

    status = "unchanged" if already else "updated"
    if json_output:
        emit_json(
            "spec.precommit.enable" if enabled else "spec.precommit.disable",
            status,
            {"pre_commit": enabled, "workspace": str(root)},
        )
        raise typer.Exit(0)

    from vaultspec_core.console import get_console

    console = get_console()
    if enabled:
        console.print(
            f"[green]{status}[/green]: vaultspec-core scaffolds "
            ".pre-commit-config.yaml in this workspace."
        )
    else:
        console.print(
            f"[green]{status}[/green]: vaultspec-core will not scaffold "
            ".pre-commit-config.yaml in this workspace."
        )
        console.print(
            "  [dim]Any existing .pre-commit-config.yaml is left in place; "
            "delete it yourself if you no longer want it.[/dim]"
        )
    raise typer.Exit(0)


@precommit_app.command("disable")
def cmd_precommit_disable(
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    target: TargetOption = None,
) -> None:
    """Decline vaultspec-managed .pre-commit-config.yaml scaffolding.

    Records hooks.pre_commit = false in the committed
    .vaultspec/workspace.json, so no later install or sync regenerates the
    file, and the vaultspec-managed .gitignore block starts ignoring it so a
    resurrected copy cannot be committed by accident. For projects that run
    their gates explicitly and forbid a commit hook. Any existing
    .pre-commit-config.yaml is left on disk untouched.
    """
    _set_precommit_policy(enabled=False, json_output=json_output, target=target)


@precommit_app.command("enable")
def cmd_precommit_enable(
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    target: TargetOption = None,
) -> None:
    """Restore vaultspec-managed .pre-commit-config.yaml scaffolding.

    Clears a previously recorded opt-out so the next install or sync scaffolds
    the canonical hooks again. This is the default for a workspace that has
    never declared a preference, so running it there is a no-op.
    """
    _set_precommit_policy(enabled=True, json_output=json_output, target=target)


@precommit_app.command("migrate")
def cmd_precommit_migrate(
    remove_yaml: Annotated[
        bool,
        typer.Option(
            "--remove-yaml",
            help=(
                "Also delete the superseded .pre-commit-config.yaml once the "
                "canonical hooks are verifiably present in prek.toml"
            ),
        ),
    ] = False,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Preview without writing")
    ] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    target: TargetOption = None,
) -> None:
    """Transplant the canonical vaultspec hooks into prek.toml.

    When prek.toml owns the hook boundary, sync no longer scaffolds
    .pre-commit-config.yaml and prek silently ignores it. This command
    renders the canonical hook set into a vaultspec-managed block inside
    prek.toml. Idempotent: re-running with the hooks already present is a
    no-op. The superseded YAML config is never deleted unless
    --remove-yaml is passed and the hooks are verified present.
    """
    apply_target(target)
    from vaultspec_core.core.prek_boundary import migrate_hooks_to_prek
    from vaultspec_core.core.types import get_context

    ctx = get_context()
    result = migrate_hooks_to_prek(
        ctx.target_dir, dry_run=dry_run, remove_yaml=remove_yaml
    )

    ok = result.status in ("migrated", "unchanged")
    if json_output:
        emit_json(
            "spec.precommit.migrate",
            result.status if ok else "failed",
            {
                "status": result.status,
                "detail": result.detail,
                "yaml_removed": result.yaml_removed,
                "dry_run": dry_run,
            },
        )
        raise typer.Exit(0 if ok else 1)

    from vaultspec_core.console import get_console

    console = get_console()
    prefix = "[dim](dry-run)[/dim] " if dry_run else ""
    if ok:
        style = "green" if result.status == "migrated" else "dim"
        console.print(f"{prefix}[{style}]{result.status}[/{style}]: {result.detail}")
        raise typer.Exit(0)
    console.print(f"{prefix}[red]{result.status}[/red]: {result.detail}")
    raise typer.Exit(1)


def _set_block_policy(
    *, block: str, enabled: bool, json_output: bool, target: Path | None
) -> None:
    """Persist the workspace's policy for one managed git block.

    The one implementation behind all four verbs, which differ only by the
    block they name, the boolean they persist, and the sentence they print.
    Idempotent, and an already-satisfied request reports success, so a
    provisioning script can set the policy unconditionally.

    This is the only writer of the committed ``blocks`` key outside the two
    gestures that mean "manage this workspace again" - a fresh install and
    ``--upgrade --force``. Deleting a block stands the per-machine echo down
    and says so; it does not reach the declaration, because an inference about
    intent must not modify a file the whole team shares.
    """
    apply_target(target)
    from vaultspec_core.core.exceptions import VaultSpecError
    from vaultspec_core.core.types import get_context
    from vaultspec_core.core.workspace_mode import (
        read_blocks_declaration,
        write_blocks_declaration,
    )

    root = get_context().target_dir
    try:
        current = read_blocks_declaration(root)
        already = getattr(current, block) == enabled
        if not already:
            write_blocks_declaration(root, replace(current, **{block: enabled}))
    except (VaultSpecError, OSError) as exc:
        _handle_error(exc, json_output=json_output)
        return

    filename = f".{block}"
    status = "unchanged" if already else "updated"
    if json_output:
        emit_json(
            f"spec.{block}.enable" if enabled else f"spec.{block}.disable",
            status,
            {block: enabled, "workspace": str(root)},
        )
        raise typer.Exit(0)

    from vaultspec_core.console import get_console

    console = get_console()
    if enabled:
        console.print(
            f"[green]{status}[/green]: vaultspec-core maintains its managed "
            f"block in {filename} for this project."
        )
    else:
        console.print(
            f"[green]{status}[/green]: vaultspec-core will not maintain its "
            f"managed block in {filename} for this project."
        )
        console.print(
            f"  [dim]The declaration is committed, so every clone honours it. "
            f"Any existing {filename} is left in place.[/dim]"
        )
    raise typer.Exit(0)


@gitignore_app.command("disable")
def cmd_gitignore_disable(
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    target: TargetOption = None,
) -> None:
    """Decline the vaultspec-managed .gitignore block for the whole project.

    Records blocks.gitignore = false in the committed
    .vaultspec/workspace.json, so no later install, upgrade or sync writes the
    block, on any machine. Deleting the block by hand stands the current
    machine down but cannot travel: the manifest that would record it is
    itself inside the block. Any existing .gitignore is left on disk untouched.
    """
    _set_block_policy(
        block="gitignore", enabled=False, json_output=json_output, target=target
    )


@gitignore_app.command("enable")
def cmd_gitignore_enable(
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    target: TargetOption = None,
) -> None:
    """Restore the vaultspec-managed .gitignore block for the whole project.

    Clears a recorded decline so the next install, upgrade or sync writes the
    block again. This is the default for a workspace that has never declared a
    preference, so running it there is a no-op.
    """
    _set_block_policy(
        block="gitignore", enabled=True, json_output=json_output, target=target
    )


@gitattributes_app.command("disable")
def cmd_gitattributes_disable(
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    target: TargetOption = None,
) -> None:
    """Decline the vaultspec-managed .gitattributes block for the whole project.

    Records blocks.gitattributes = false in the committed
    .vaultspec/workspace.json. The block's default entries normalise line
    endings for every clone, so declining it is a team-wide statement and
    belongs in a committed file rather than on one machine.
    """
    _set_block_policy(
        block="gitattributes", enabled=False, json_output=json_output, target=target
    )


@gitattributes_app.command("enable")
def cmd_gitattributes_enable(
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    target: TargetOption = None,
) -> None:
    """Restore the vaultspec-managed .gitattributes block for the whole project.

    Clears a recorded decline so the next install, upgrade or sync writes the
    block again. This is the default, so running it on a workspace that has
    never declared a preference is a no-op.
    """
    _set_block_policy(
        block="gitattributes", enabled=True, json_output=json_output, target=target
    )

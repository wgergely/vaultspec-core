"""CLI surface for the schema migration registry.

Exposes ``vaultspec-core migrations status`` (read-only) and
``vaultspec-core migrations run`` (explicit trigger). Both commands
operate on the workspace selected by the global ``--target`` option.
"""

from __future__ import annotations

import json as _json
import logging
from typing import TYPE_CHECKING, Annotated

import typer

from vaultspec_core.cli._app import make_app
from vaultspec_core.cli._target import TargetOption, apply_target
from vaultspec_core.cli.json_output import json_format_kwargs

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from vaultspec_core.migrations import DeletionPreview

logger = logging.getLogger(__name__)

#: How many doomed paths the human surface lists before it summarises the
#: rest. A fold on the measured production corpus removes thousands of
#: records; an operator deciding whether to proceed needs the shape and the
#: count, and the exhaustive list is one ``--json`` away.
_PREVIEW_LIMIT = 20

migrations_app = make_app(
    help="Inspect and run vaultspec-core schema migrations",
    no_args_is_help=True,
    add_completion=False,
)


@migrations_app.command("status")
def cmd_migrations_status(
    target: TargetOption = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Show registered migrations and which entries are pending.

    Reads the workspace manifest's ``vaultspec_version`` and lists
    every registered migration plus the subset whose ``target_version``
    exceeds it. Read-only; never mutates the workspace.

    Exit codes: ``0`` when the workspace is up to date or has no
    manifest, ``1`` when migrations are pending.
    """
    apply_target(target)

    from vaultspec_core.core.manifest import read_manifest_data
    from vaultspec_core.core.types import get_context
    from vaultspec_core.migrations import (
        REGISTRY,
        MigrationStatus,
        list_pending,
        migration_status,
    )

    root_dir = get_context().target_dir
    mdata = read_manifest_data(root_dir)
    manifest_version = mdata.vaultspec_version
    status, _pending_names = migration_status(root_dir, manifest=mdata)

    pending = list_pending(root_dir, manifest=mdata)

    if json_output:
        from vaultspec_core.cli.rendering import json_envelope

        payload = {
            "manifest_version": manifest_version,
            "status": status.value,
            "registered": [
                {"name": m.name, "target_version": m.target_version} for m in REGISTRY
            ],
            "pending": [
                {"name": m.name, "target_version": m.target_version} for m in pending
            ],
        }
        envelope = json_envelope("migrations.status", "unchanged", payload)
        typer.echo(_json.dumps(envelope, **json_format_kwargs()))
        raise typer.Exit(code=0 if status != MigrationStatus.PENDING else 1)

    from vaultspec_core.cli.rendering import (
        Cell,
        Column,
        render_listing,
        summary_line,
    )

    # No manifest baseline: applied state is genuinely unknowable, so do not
    # assert that any entry has been applied (issue #121). Labelling everything
    # "applied" here previously hid truly-pending migrations.
    state_style = {"unknown": "dim", "pending": "yellow", "applied": "green"}
    states: list[str] = []
    rows: list[dict[str, object]] = []
    for m in REGISTRY:
        if status == MigrationStatus.UNKNOWN:
            state = "unknown"
        elif m in pending:
            state = "pending"
        else:
            state = "applied"
        states.append(state)
        rows.append(
            {
                "state": Cell(state, state_style[state]),
                "version": m.target_version,
                "name": m.name,
            }
        )
    breakdown = [
        (states.count(label), label) for label in ("applied", "pending", "unknown")
    ]
    render_listing(
        rows,
        [Column("state"), Column("version"), Column("name")],
        title=f"Migrations  (status {status.value}, manifest "
        f"{manifest_version or 'unset'})",
        summary=summary_line(len(rows), "registered", breakdown),
        empty="no migrations registered",
    )
    if status == MigrationStatus.PENDING:
        from vaultspec_core.cli.rendering import hints_suppressed, render_next_actions

        if not hints_suppressed():
            render_next_actions(
                [
                    (
                        "Preview what the pending migrations would remove",
                        "vaultspec-core migrations run --dry-run",
                    ),
                    ("Apply the pending migrations", "vaultspec-core migrations run"),
                ]
            )
        raise typer.Exit(code=1)
    raise typer.Exit(code=0)


def _render_deletion_preview(previews: list[DeletionPreview], *, doomed: int) -> None:
    """Print the deletion set for a human, capped at :data:`_PREVIEW_LIMIT`."""
    from vaultspec_core.console import get_console

    console = get_console()
    shown = 0
    for preview in previews:
        if not preview.previewable:
            console.print(
                f"  [yellow]{preview.name}[/yellow]: cannot enumerate its deletions"
            )
            continue
        if not preview.paths:
            continue
        console.print(
            f"  [bold]{preview.name}[/bold] removes {len(preview.paths)} document(s):"
        )
        for path in preview.paths:
            if shown >= _PREVIEW_LIMIT:
                break
            console.print(f"    [red]-[/red] {path}")
            shown += 1
    if doomed > shown:
        console.print(f"    [dim]... and {doomed - shown} more[/dim]")


def _preview_payload(previews: list[DeletionPreview]) -> list[dict[str, object]]:
    """Convert deletion previews to the ``--json`` shape."""
    return [
        {
            "name": preview.name,
            "target_version": preview.target_version,
            "previewable": preview.previewable,
            "deletes": [str(path) for path in preview.paths],
        }
        for preview in previews
    ]


def _confirm_deletions(
    doomed: int,
    *,
    json_output: bool,
    interactive: bool | None = None,
    confirm_fn: Callable[[str], bool] | None = None,
) -> bool:
    """Decide whether a destructive run may proceed without ``--yes``.

    Interactive terminals are asked. Every other context - CI, a piped
    stdin, an MCP or agent invocation, ``--json`` - is told and proceeds.
    Two reasons for proceeding rather than failing closed. First,
    ``migrations run`` is only ever *one* of the registry's triggers: the
    same entries run from ``install --upgrade`` and lazily from every
    ``vault`` command, so failing the explicit operator verb closed would
    push a blocked script onto a trigger with no gate at all, making the
    least safe path the path of least resistance. Second, the deletion is
    now recoverable - every removed document is copied into
    ``.vault/.trash/`` first - so the prompt guards against surprise, not
    against loss, and surprise is not something a non-interactive caller
    experiences. Hanging is never an option either way:
    :func:`sys.stdin.isatty` is consulted before anything reads stdin.

    Args:
        doomed: How many documents the pending migrations would delete.
        json_output: Whether the caller asked for machine output.
        interactive: Override for whether a human is at the other end;
            defaults to :func:`sys.stdin.isatty`, matching the convention
            the resource-sync prompts already follow.
        confirm_fn: The prompt to ask with; defaults to
            :func:`typer.confirm`.

    Returns:
        ``True`` to proceed, ``False`` when an operator declined.
    """
    import sys

    from vaultspec_core.console import get_console

    at_terminal = interactive if interactive is not None else sys.stdin.isatty()
    if json_output or not at_terminal:
        get_console().print(
            f"[yellow]warning[/yellow]: removing {doomed} document(s); copies "
            "are kept under .vault/.trash/"
        )
        return True
    ask = confirm_fn if confirm_fn is not None else typer.confirm
    return ask(f"Remove {doomed} document(s)? Copies are kept under .vault/.trash/")


def _fail(exc: Exception, *, json_output: bool) -> None:
    """Report a failed migration run on the surface the caller asked for.

    A domain refusal carries the remedy on the exception, not in the
    message. The corrupt-manifest guard is the case that made this matter:
    it refuses where the driver previously replayed the whole registry, and
    the operator needs to be told to delete the manifest and re-run install,
    not just that something failed (issue #455). The refusal to delete
    without a backup reaches the operator the same way.
    """
    hint = getattr(exc, "hint", "")
    if json_output:
        from vaultspec_core.cli.rendering import json_envelope

        payload: dict[str, str] = {"error": str(exc)}
        if hint:
            payload["hint"] = hint
        typer.echo(
            _json.dumps(
                json_envelope("migrations.run", "failed", payload),
                **json_format_kwargs(),
            )
        )
    else:
        typer.echo(f"Error: migration failed: {exc}", err=True)
        if hint:
            typer.echo(f"  Hint: {hint}", err=True)


def _emit_dry_run(
    previews: list[DeletionPreview], *, doomed: int, json_output: bool
) -> None:
    """Report what a real run would delete, having changed nothing."""
    from vaultspec_core.console import get_console

    if json_output:
        from vaultspec_core.cli.rendering import json_envelope

        payload: dict[str, object] = {
            "dry_run": True,
            "deletes": doomed,
            "migrations": _preview_payload(previews),
        }
        typer.echo(
            _json.dumps(
                json_envelope("migrations.run", "unchanged", payload),
                **json_format_kwargs(),
            )
        )
        return

    console = get_console()
    if not previews:
        console.print("[dim]unchanged[/dim]: no pending migrations.")
        return
    console.print(
        "[bold]Pending migrations[/bold]: "
        + ", ".join(preview.name for preview in previews)
    )
    if not doomed:
        console.print("[green]No documents would be removed.[/green]")
        return
    console.print(f"[bold]Would remove {doomed} document(s):[/bold]")
    _render_deletion_preview(previews, doomed=doomed)
    console.print(
        "[dim]A real run copies each of these into .vault/.trash/ before "
        "removing it.[/dim]"
    )


def _pending_deletions(root_dir: Path) -> list[DeletionPreview]:
    """Enumerate what the pending migrations would delete from *root_dir*."""
    from vaultspec_core.migrations import preview_deletions

    return preview_deletions(root_dir)


@migrations_app.command("run")
def cmd_migrations_run(
    target: TargetOption = None,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="List every document the pending migrations would delete",
        ),
    ] = False,
    assume_yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Skip the confirmation for deletions"),
    ] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Run pending schema migrations and bump the manifest version.

    Executes every registered migration whose ``target_version``
    exceeds the manifest's ``vaultspec_version``. On success bumps
    ``vaultspec_version`` to the running package version. A migration
    that raises stops the run and leaves the manifest unchanged so the
    next invocation re-attempts.

    Deletions. Some migrations remove documents. ``--dry-run`` lists every
    one of them and changes nothing; the enumeration comes from the same
    planner the real run applies, so it previews the run rather than
    describing it. Without ``--dry-run`` an interactive terminal is asked
    to confirm unless ``--yes`` is passed, and either way every removed
    document is copied into ``.vault/.trash/`` before it is unlinked.

    Exit codes: ``0`` on success (including the no-pending no-op and every
    dry run), ``1`` if any migration raised or an operator declined.
    """
    apply_target(target)

    from vaultspec_core.cli.rendering import Outcome, OutcomeItem, emit_outcomes
    from vaultspec_core.console import get_console
    from vaultspec_core.core.types import get_context
    from vaultspec_core.migrations import run_pending_migrations

    root_dir = get_context().target_dir

    try:
        previews = _pending_deletions(root_dir)
    except Exception as exc:
        _fail(exc, json_output=json_output)
        raise typer.Exit(code=1) from exc
    doomed = sum(len(preview.paths) for preview in previews)

    if dry_run:
        _emit_dry_run(previews, doomed=doomed, json_output=json_output)
        raise typer.Exit(code=0)

    if doomed and not assume_yes:
        if not json_output:
            get_console().print(
                "[bold]Pending migrations would remove these documents:[/bold]"
            )
            _render_deletion_preview(previews, doomed=doomed)
        if not _confirm_deletions(doomed, json_output=json_output):
            get_console().print("[dim]aborted[/dim]: nothing was changed.")
            raise typer.Exit(code=1)

    try:
        results = run_pending_migrations(root_dir)
    except Exception as exc:
        _fail(exc, json_output=json_output)
        raise typer.Exit(code=1) from exc

    outcomes = [
        OutcomeItem(
            name=r.name,
            outcome=Outcome.UPDATED,
            detail=f"{r.target_version}  {r.summary}",
        )
        for r in results
    ]

    if not outcomes and not json_output:
        get_console().print("[dim]unchanged[/dim]: no pending migrations.")
        raise typer.Exit(code=0)

    if not json_output:
        for result in results:
            if result.snapshot:
                get_console().print(
                    f"[dim]backup[/dim]: removed documents copied to {result.snapshot}"
                )

    raise typer.Exit(
        emit_outcomes(
            outcomes,
            command="migrations.run",
            title="Migrations",
            json_output=json_output,
        )
    )

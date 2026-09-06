"""CLI surface for the schema migration registry.

Exposes ``vaultspec-core migrations status`` (read-only) and
``vaultspec-core migrations run`` (explicit trigger). Both commands
operate on the workspace selected by the global ``--target`` option.
"""

from __future__ import annotations

import json as _json
import logging
from typing import Annotated

import typer

from vaultspec_core.cli._app import make_app
from vaultspec_core.cli._target import TargetOption, apply_target
from vaultspec_core.cli.json_output import json_format_kwargs

logger = logging.getLogger(__name__)

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
                [("Apply the pending migrations", "vaultspec-core migrations run")]
            )
        raise typer.Exit(code=1)
    raise typer.Exit(code=0)


@migrations_app.command("run")
def cmd_migrations_run(
    target: TargetOption = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Run pending schema migrations and bump the manifest version.

    Executes every registered migration whose ``target_version``
    exceeds the manifest's ``vaultspec_version``. On success bumps
    ``vaultspec_version`` to the running package version. A migration
    that raises stops the run and leaves the manifest unchanged so the
    next invocation re-attempts.

    Exit codes: ``0`` on success (including the no-pending no-op),
    ``1`` if any migration raised.
    """
    apply_target(target)

    from vaultspec_core.cli.rendering import Outcome, OutcomeItem, emit_outcomes
    from vaultspec_core.console import get_console
    from vaultspec_core.core.types import get_context
    from vaultspec_core.migrations import run_pending_migrations

    root_dir = get_context().target_dir

    try:
        results = run_pending_migrations(root_dir)
    except Exception as exc:
        # A domain refusal carries the remedy on the exception, not in the
        # message. The corrupt-manifest guard is the case that made this
        # matter: it refuses where the driver previously replayed the whole
        # registry, and the operator needs to be told to delete the manifest
        # and re-run install, not just that something failed (issue #455).
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

    raise typer.Exit(
        emit_outcomes(
            outcomes,
            command="migrations.run",
            title="Migrations",
            json_output=json_output,
        )
    )

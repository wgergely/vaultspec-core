"""Top-level ``status`` verb: the zeroth-move orientation surface.

``vaultspec-core status`` with no argument renders the vault-wide rollup
(plans in flight, recently completed, recent changes, active features,
totals); with a TARGET (plan stem, plan path, or feature handle) it renders
that target's grounding trace. The verb is read-only, produces no artifact,
and keeps the graph an implementation detail behind the orientation data
core in :mod:`vaultspec_core.vaultcore.orientation`.

The verb is registered onto the root app by :func:`register`; it is the
top-level orientation entry point and does not live under the ``vault`` group.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, NoReturn

import typer

from vaultspec_core.cli._target import TargetOption, apply_target
from vaultspec_core.cli.json_output import json_format_kwargs

if TYPE_CHECKING:
    from pathlib import Path
    from typing import Any

    import typer as _typer
    from rich.console import Console

    from vaultspec_core.core.diagnosis.collectors_companion import (
        CompanionCapability,
    )
    from vaultspec_core.vaultcore.orientation import (
        GroundingTrace,
        PlanInFlight,
        PlanTrace,
        Rollup,
        StepTrace,
    )


def register(app: _typer.Typer) -> None:
    """Mount the top-level ``status`` command onto *app*."""
    app.command("status")(cmd_status)


def _fail(console: Console, message: str, *, json_output: bool) -> NoReturn:
    """Report a pre-render failure, then exit with code 1.

    Mirrors the ``vaultspec.error.v1`` envelope :func:`apply_target` emits
    for a workspace-resolution failure, so a graph-read or target-resolution
    failure is equally parseable under ``--json``: the envelope is the only
    thing written to stdout, and text-mode diagnostics never reach it.
    """
    if json_output:
        import json

        from vaultspec_core.cli.rendering import json_envelope

        envelope = json_envelope("error", "failed", {"message": message})
        print(json.dumps(envelope, **json_format_kwargs()))
    else:
        console.print(f"[red]{message}[/red]")
    raise typer.Exit(code=1)


def cmd_status(
    target_arg: Annotated[
        str | None,
        typer.Argument(
            metavar="[TARGET]",
            help=(
                "Optional plan stem, plan path, or feature handle. When "
                "given, renders the grounding trace for that target instead "
                "of the vault-wide rollup."
            ),
        ),
    ] = None,
    limit: Annotated[
        int,
        typer.Option("--limit", help="Number of recent documents to show (rollup)"),
    ] = 10,
    since: Annotated[
        int | None,
        typer.Option(
            "--since",
            help="Show documents modified within this many days (rollup)",
        ),
    ] = None,
    paths: Annotated[
        bool,
        typer.Option(
            "--paths",
            help="Show each referenced document's path in the trace (target mode)",
        ),
    ] = False,
    verbose_exec: Annotated[
        bool,
        typer.Option(
            "--verbose-exec",
            help="List execution records individually instead of collapsing "
            "them per feature (rollup).",
        ),
    ] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    no_hints: Annotated[
        bool, typer.Option("--no-hints", help="Suppress next-step advisory hints")
    ] = False,
    target: TargetOption = None,
) -> None:
    """Orient in a vaultspec vault: rollup, or a grounding trace for a target.

    With no argument, renders the vault-wide rollup: plans in flight with a
    one-line overview, recently completed plans, recent changes grouped by
    type, active features, and totals. With a TARGET (a plan stem, plan
    path, or feature handle), renders that target's grounding trace: a
    plan-line header, each step's check-state mapped to its execution
    record, plus grounding documents grouped by type. Read-only: it never
    writes and produces no artifact.
    """
    apply_target(target, json_output=json_output)
    from vaultspec_core.console import get_console
    from vaultspec_core.core.types import get_context as _get_ctx
    from vaultspec_core.graph import VaultGraph
    from vaultspec_core.vaultcore.orientation import (
        TargetResolutionError,
        compute_rollup,
        compute_trace,
    )

    console = get_console()
    root_dir = _get_ctx().target_dir

    try:
        graph = VaultGraph(root_dir)
    except OSError as exc:
        _fail(console, f"Error reading vault: {exc}", json_output=json_output)

    if target_arg is not None:
        try:
            trace = compute_trace(root_dir, target_arg, graph=graph, with_paths=paths)
        except TargetResolutionError as exc:
            _fail(console, str(exc), json_output=json_output)
        _emit_status_trace(
            console, trace, paths=paths, json_output=json_output, no_hints=no_hints
        )
        return

    rollup = compute_rollup(
        root_dir,
        limit=limit,
        since_days=since,
        verbose_exec=verbose_exec,
        graph=graph,
    )
    _emit_status_rollup(
        console,
        rollup,
        json_output=json_output,
        no_hints=no_hints,
        companion=_safe_companion(root_dir),
    )


# The rollup's human rendering shows at most this many active features;
# a vault that archives nothing would otherwise list every feature it has
# ever carried, flooding the orientation view. The JSON payload is uncapped.
_ACTIVE_FEATURES_DISPLAY_CAP = 10

# Advisory hint pairs (description, command) for the status verb's two
# modes. The rollup points at the targeted mode and at health diagnosis;
# the trace points at graph exploration and the deep single-plan validator.
_STATUS_ROLLUP_HINTS: tuple[tuple[str, str], ...] = (
    (
        "Trace a plan's steps, records, and grounding documents",
        "vaultspec-core status <plan-or-feature>",
    ),
    (
        "Diagnose workspace health",
        "vaultspec-core spec doctor",
    ),
)


def _status_trace_hints(trace: GroundingTrace) -> tuple[tuple[str, str], ...]:
    """Build the trace-mode hint pairs, naming the target's feature."""
    feature = next((plan.feature for plan in trace.plans if plan.feature), None)
    feature_arg = feature or "<tag>"
    plan_arg = trace.plans[0].stem if trace.plans else "<path>"
    return (
        (
            "Explore the full relationship graph for this feature",
            f"vaultspec-core vault graph --feature {feature_arg}",
        ),
        (
            "Validate a single plan's structure and step state",
            f"vaultspec-core vault plan status {plan_arg}",
        ),
    )


def _emit_status_hints(
    pairs: tuple[tuple[str, str], ...],
    *,
    json_output: bool,
    no_hints: bool,
) -> list[dict[str, str]] | None:
    """Render advisory hint lines for status, returning the JSON shape."""
    from vaultspec_core.cli.rendering import hints_suppressed, render_next_actions

    if hints_suppressed(no_hints):
        return None

    hints = [{"text": text, "command": command} for text, command in pairs]
    if not json_output:
        render_next_actions(pairs)
    return hints


def _plan_cells(plan: PlanInFlight) -> list[str]:
    """Clean plan-line cells for a rollup row, with a trailing recency cell."""
    from vaultspec_core.cli.rendering import plan_line_cells

    cells = plan_line_cells(
        name=plan.stem,
        tier=plan.tier,
        waves_completed=plan.waves_completed,
        wave_count=plan.wave_count,
        phases_completed=plan.phases_completed,
        phase_count=plan.phase_count,
        steps_completed=plan.closed_steps,
        step_count=plan.total_steps,
        completion_percent=plan.completion_percent,
        next_open_step=plan.next_open_step,
        exec_missing=plan.exec_missing,
    )
    cells.append(plan.modified or "")
    return cells


def _safe_companion(root_dir: Path) -> CompanionCapability | None:
    """Probe the semantic-search companion for the orientation surface.

    Whether semantic search is available here is orientation data: it decides
    which discovery move an agent should reach for first. Swallowing a failure
    is right for the same reason the doctor's guard is - status must never fail
    because the newest collector on it did.
    """
    from vaultspec_core.core.diagnosis.collectors_companion import (
        collect_companion_capability,
    )

    try:
        return collect_companion_capability(root_dir)
    except Exception:
        return None


def _companion_line(cap: CompanionCapability) -> str:
    """Render the one-line orientation summary for *cap*.

    Deliberately states provisioning and names the companion's own health
    command rather than implying core checked liveness, which it did not.
    """
    from vaultspec_core.core.diagnosis.collectors_companion import CompanionSignal

    if cap.signal is CompanionSignal.ABSENT:
        return (
            f"  [dim]{cap.package} not provisioned - "
            f"use find and grep for discovery[/dim]"
        )
    version = f" {cap.version}" if cap.version else ""
    floor_note = (
        f"  [yellow]below advisory floor {cap.floor}[/yellow]"
        if cap.signal is CompanionSignal.BELOW_FLOOR
        else ""
    )
    return (
        f"  [green]{cap.package}{version} provisioned[/green]{floor_note}  "
        f"[dim]liveness: {cap.health_authority}[/dim]"
    )


def _rollup_payload(
    rollup: Rollup, companion: CompanionCapability | None = None
) -> dict[str, Any]:
    """Shape a :class:`Rollup` into the JSON envelope's data mapping."""
    import dataclasses

    return {
        "companion": dataclasses.asdict(companion) if companion else None,
        "active_features": [dataclasses.asdict(f) for f in rollup.active_features],
        "active_features_total": rollup.active_features_total,
        "active_features_truncated": (
            len(rollup.active_features) < rollup.active_features_total
        ),
        "plans_in_flight": [dataclasses.asdict(p) for p in rollup.plans_in_flight],
        "recently_completed": [
            dataclasses.asdict(p) for p in rollup.recently_completed
        ],
        "recent_documents": {
            doc_type: [dataclasses.asdict(d) for d in docs]
            for doc_type, docs in rollup.recent_documents.items()
        },
        "exec_activity": [dataclasses.asdict(a) for a in rollup.exec_activity],
        "totals": rollup.totals,
        "limit": rollup.limit,
        "since_days": rollup.since_days,
    }


def _emit_status_rollup(
    console: Console,
    rollup: Rollup,
    *,
    json_output: bool,
    no_hints: bool,
    companion: CompanionCapability | None = None,
) -> None:
    """Render the vault-wide rollup as text or JSON."""
    if json_output:
        import json

        from vaultspec_core.cli.rendering import json_envelope

        hints = _emit_status_hints(
            _STATUS_ROLLUP_HINTS, json_output=True, no_hints=no_hints
        )
        envelope = json_envelope(
            "vault.status",
            "unchanged",
            _rollup_payload(rollup, companion),
            hints={"next_steps": hints} if hints is not None else None,
        )
        typer.echo(json.dumps(envelope, **json_format_kwargs(), default=str))
        return

    from vaultspec_core.cli.rendering import (
        active_feature_tail,
        align_plan_rows,
    )

    console.print("[bold]Vault Status[/bold]")

    console.print()
    console.print("[bold]Plans in flight[/bold]  [dim](at least one open step)[/dim]")
    if rollup.plans_in_flight:
        for line in align_plan_rows([_plan_cells(p) for p in rollup.plans_in_flight]):
            console.print(f"  {line}")
    else:
        console.print("  [dim]none[/dim]")

    if rollup.recently_completed:
        console.print()
        console.print("[bold]Recently completed[/bold]")
        for line in align_plan_rows(
            [_plan_cells(p) for p in rollup.recently_completed]
        ):
            console.print(f"  {line}")

    console.print()
    console.print("[bold]Recent changes[/bold]")
    if rollup.recent_documents:
        for doc_type in sorted(rollup.recent_documents):
            console.print(f"  [bold dim]{doc_type}[/bold dim]")
            for doc in rollup.recent_documents[doc_type]:
                modified = f"  [dim]{doc.modified}[/dim]" if doc.modified else ""
                console.print(f"    {doc.stem}{modified}")
    else:
        console.print("  [dim]none[/dim]")

    if rollup.exec_activity:
        console.print()
        console.print("[bold]Execution activity[/bold]  [dim](per feature)[/dim]")
        for activity in rollup.exec_activity:
            feature = activity.feature or "(no feature)"
            latest = f"  [dim]{activity.latest}[/dim]" if activity.latest else ""
            records = "record" if activity.count == 1 else "records"
            console.print(
                f"  {feature}  [cyan]{activity.count} {records}[/cyan]{latest}"
            )

    console.print()
    console.print("[bold]Active features[/bold]")
    if rollup.active_features:
        shown = rollup.active_features[:_ACTIVE_FEATURES_DISPLAY_CAP]
        for feat in shown:
            plan_marker = " [green]plan[/green]" if feat.has_plan else ""
            tail = active_feature_tail(
                tier=feat.plan_tier,
                steps_completed=feat.plan_steps_completed,
                step_count=feat.plan_step_count,
                completion_percent=feat.plan_completion_percent,
                plan_count=feat.plan_count,
                plans_unreadable=feat.plans_unreadable,
            )
            tail_str = f"  [cyan]{tail}[/cyan]" if tail else ""
            activity = (
                f"  [dim]{feat.latest_activity}[/dim]" if feat.latest_activity else ""
            )
            console.print(
                f"  [bold]{feat.name}[/bold]  {feat.doc_count} docs"
                f"{plan_marker}{tail_str}{activity}"
            )
        remainder = rollup.active_features_total - len(shown)
        if remainder > 0:
            console.print(
                f"  [dim]... and {remainder} more  "
                f"> vaultspec-core vault feature list[/dim]"
            )
    else:
        console.print("  [dim]none[/dim]")

    if companion is not None:
        console.print()
        console.print("[bold]Discovery[/bold]")
        console.print(_companion_line(companion))

    totals = rollup.totals
    console.print()
    console.print("[bold]Totals[/bold]")
    console.print(f"  Total documents: {totals.get('total_docs', 0)}")
    console.print(f"  Total features:  {totals.get('total_features', 0)}")

    _emit_status_hints(_STATUS_ROLLUP_HINTS, json_output=False, no_hints=no_hints)


def _plan_trace_payload(plan: PlanTrace) -> dict[str, Any]:
    """Shape a :class:`PlanTrace` into the JSON envelope's data mapping."""
    import dataclasses

    return {
        "stem": plan.stem,
        "feature": plan.feature,
        "tier": plan.tier,
        "total_steps": plan.total_steps,
        "closed_steps": plan.closed_steps,
        "open_steps": plan.open_steps,
        "completion_percent": plan.completion_percent,
        "wave_count": plan.wave_count,
        "waves_completed": plan.waves_completed,
        "phase_count": plan.phase_count,
        "phases_completed": plan.phases_completed,
        "next_open_step": plan.next_open_step,
        "exec_missing": plan.exec_missing,
        "steps": [dataclasses.asdict(s) for s in plan.steps],
        "unlinked_records": list(plan.unlinked_records),
        "grounding": {k: list(v) for k, v in plan.grounding.items()},
        "error": plan.error,
    }


def _trace_header(plan: PlanTrace) -> str:
    """Render the clean plan-line header for a single traced plan."""
    from vaultspec_core.cli.rendering import plan_line_cells

    cells = plan_line_cells(
        name=plan.stem,
        tier=plan.tier,
        waves_completed=plan.waves_completed,
        wave_count=plan.wave_count,
        phases_completed=plan.phases_completed,
        phase_count=plan.phase_count,
        steps_completed=plan.closed_steps,
        step_count=plan.total_steps,
        completion_percent=plan.completion_percent,
        next_open_step=plan.next_open_step,
        exec_missing=plan.exec_missing,
    )
    return "   ".join(cell for cell in cells if cell)


def _emit_status_trace(
    console: Console,
    trace: GroundingTrace,
    *,
    paths: bool,
    json_output: bool,
    no_hints: bool,
) -> None:
    """Render the grounding trace as text or JSON."""
    hint_pairs = _status_trace_hints(trace)

    if json_output:
        import json

        from vaultspec_core.cli.rendering import json_envelope

        hints = _emit_status_hints(hint_pairs, json_output=True, no_hints=no_hints)
        envelope = json_envelope(
            "vault.status",
            "unchanged",
            {
                "target": trace.target,
                "kind": trace.kind,
                "plans": [_plan_trace_payload(p) for p in trace.plans],
                "paths": dict(trace.paths),
            },
            hints={"next_steps": hints} if hints is not None else None,
        )
        typer.echo(json.dumps(envelope, **json_format_kwargs(), default=str))
        return

    console.print(f"[bold]Grounding Trace[/bold]  {trace.target} ({trace.kind})")

    for plan in trace.plans:
        console.print()
        if plan.error:
            console.print(f"[bold]{plan.stem}[/bold]")
            console.print(f"  [red]error: {plan.error}[/red]")
            continue

        console.print(f"[bold]{_trace_header(plan)}[/bold]")

        for step in plan.steps:
            # Escape the checkbox brackets: Rich parses an unescaped ``[x]``
            # as a style tag and drops it, so a checked step would render
            # with no glyph at all.
            glyph = r"[green]\[x][/green]" if step.checked else r"[dim]\[ ][/dim]"
            cursor = ">" if step.display_path == plan.next_open_step else " "
            record = _step_evidence_cell(step)
            path = (
                f"  [dim]{trace.paths[step.record_stem]}[/dim]"
                if paths and step.record_stem and step.record_stem in trace.paths
                else ""
            )
            console.print(
                f"  [cyan]{cursor}[/cyan] {glyph} {step.display_path}  {record}{path}"
            )

        _emit_stem_group(
            console,
            "unlinked records",
            plan.unlinked_records,
            trace,
            paths,
            style="yellow",
        )

        if plan.grounding:
            console.print("  [bold dim]grounding[/bold dim]")
            for doc_type in sorted(plan.grounding):
                for stem in plan.grounding[doc_type]:
                    path = (
                        f"  [dim]{trace.paths[stem]}[/dim]"
                        if paths and stem in trace.paths
                        else ""
                    )
                    console.print(f"    [dim]{doc_type}[/dim]  {stem}{path}")

    _emit_status_hints(hint_pairs, json_output=False, no_hints=no_hints)


def _step_evidence_cell(step: StepTrace) -> str:
    """Render the evidence column of one trace row.

    A ledger-mapped step reads ``ledger N rows`` plus its ``verify:`` state;
    a step mapped by a legacy per-Step record shows that record's stem; a
    closed step with no rows is ``unlinked``; an open one is ``no rows``.
    """
    if step.record_stem and step.rows is not None:
        noun = "row" if step.rows == 1 else "rows"
        cell = f"ledger {step.rows} {noun}"
        if step.verify == "pass":
            cell += "  [green]verify:pass[/green]"
        elif step.verify == "fail":
            cell += "  [red]verify:fail[/red]"
        return cell
    if step.record_stem:
        return step.record_stem
    if step.checked:
        return "[yellow]unlinked[/yellow]"
    return "[dim]no rows[/dim]"


def _emit_stem_group(
    console: Console,
    label: str,
    stems: list[str],
    trace: GroundingTrace,
    paths: bool,
    *,
    style: str = "",
) -> None:
    """Render a labelled list of stems, optionally with their paths."""
    if not stems:
        return
    console.print(f"  [bold dim]{label}[/bold dim]")
    for stem in stems:
        text = f"[{style}]{stem}[/{style}]" if style else stem
        path = (
            f"  [dim]{trace.paths[stem]}[/dim]" if paths and stem in trace.paths else ""
        )
        console.print(f"    {text}{path}")

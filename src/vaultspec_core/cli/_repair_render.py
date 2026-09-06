"""Presentation layer for the ``vaultspec-core vault repair`` pipeline.

Turns a :class:`vaultspec_core.vaultcore.repair.RepairRun` into either the
operator-facing console report (:func:`render_repair_run`) or the ``--json``
payload (:func:`repair_payload`). Pure rendering: nothing here touches the
filesystem or mutates the run, so :mod:`.vault_cmd` keeps only the Typer
wiring for the ``repair`` verb.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from vaultspec_core.core.windowing import windowed_section

if TYPE_CHECKING:
    from rich.console import Console

    from vaultspec_core.vaultcore.repair import RepairRun


#: Maximum rows carried per growing report section. These bound BOTH
#: surfaces now: the same constant caps the text rendering and the machine
#: payload, so the two cannot disagree about what was withheld.
_PLANNED_FIX_LIMIT = 20
_CHANGED_FILE_LIMIT = 30
_UNRESOLVED_LIMIT = 20
_DIAGNOSTIC_LIMIT = 10

#: Journal entries carried on the machine surface. The journal has no human
#: cap because it is not rendered; it is bounded here because it grows with
#: the repair.
_JOURNAL_LIMIT = 50


def repair_payload(run: RepairRun) -> dict[str, Any]:
    """Convert a :class:`RepairRun` to a JSON-serializable mapping.

    Every section that grows with the size of the repair is bounded by the
    same limit its human rendering uses, and carries the window fields that
    say what was withheld. Previously the human surface capped these lists
    while the machine payload returned them whole - measured at 850,927 bytes
    against 4,479 bytes of text output on a vault with 5% of its documents
    damaged, a 190x gap for a preview that changes nothing, from a payload
    that carried the same findings across several sections.

    Payload size grows with how broken the vault is, so the unbounded form
    was largest exactly when the caller could least afford it.

    Args:
        run: The completed repair run.

    Returns:
        The ``vault.repair`` v2 payload: unbounded sections become
        ``{items, returned, total, truncated, next_offset?}`` objects; scalar
        counts are unchanged.
    """
    return {
        "dry_run": run.dry_run,
        "feature": run.feature,
        "include_index": run.include_index,
        "partial_failure": run.partial_failure,
        "phases": run.phases,
        "journal": windowed_section(run.journal, limit=_JOURNAL_LIMIT),
        "changed_files": windowed_section(run.changed_files, limit=_CHANGED_FILE_LIMIT),
        "generated_indexes": windowed_section(
            run.generated_indexes, limit=_CHANGED_FILE_LIMIT
        ),
        "planned_fixes": windowed_section(run.planned_fixes, limit=_PLANNED_FIX_LIMIT),
        "unresolved": windowed_section(run.unresolved, limit=_UNRESOLVED_LIMIT),
        "root_causes": windowed_section(run.root_causes, limit=_UNRESOLVED_LIMIT),
        "error_count": run.error_count,
        "warning_count": run.warning_count,
        "fixed_count": run.fixed_count,
    }


def render_repair_run(run: RepairRun, *, verbose: bool = False) -> None:
    """Render a repair run for human operators."""
    from vaultspec_core.console import get_console

    console = get_console()
    _render_heading(console, run)
    for phase in run.phases:
        _render_phase(console, phase, verbose=verbose)
    _render_planned_fixes(console, run)
    _render_root_causes(console, run)
    _render_changed_files(console, run)
    _render_unresolved(console, run, verbose=verbose)


def _render_heading(console: Console, run: RepairRun) -> None:
    title = "Vault Repair Preview" if run.dry_run else "Vault Repair"
    if run.feature:
        title += f" - #{run.feature}"
    console.print(f"[bold]{title}[/bold]")
    if run.partial_failure:
        console.print("[red]  partial repair: at least one phase failed[/red]")


def _render_phase(console: Console, phase: dict[str, Any], *, verbose: bool) -> None:
    """Dispatch one pipeline phase to its renderer; unknown phases are silent."""
    name = phase.get("phase", "unknown")
    if name == "preflight":
        _render_preflight_phase(console, phase)
        return
    if name in {"check", "fix", "postcheck"}:
        _render_check_phase(console, phase, verbose=verbose)
        return
    if name == "index":
        _render_index_phase(console, phase, verbose=verbose)
        return
    if name == "summary":
        _render_summary_phase(console, phase)


def _render_preflight_phase(console: Console, phase: dict[str, Any]) -> None:
    status = phase.get("migration_status", "unknown")
    platform = phase.get("platform", {})
    case_probe = platform.get("case_sensitive_probe", "unknown")
    console.print(f"  [bold]preflight[/bold]: migrations {status}")
    console.print(f"    filesystem case probe: {case_probe}")
    pending = phase.get("pending_migrations", [])
    if pending:
        console.print(f"    pending migrations: {', '.join(pending)}")
    _render_pending_deletions(console, phase)
    for migration in phase.get("applied_migrations", []):
        console.print(f"    applied migration: {migration['summary']}")
    for snapshot in phase.get("snapshots", []):
        console.print(f"    [dim]removed documents copied to {snapshot}[/dim]")
    if phase.get("message"):
        console.print(f"    [yellow]{phase['message']}[/yellow]")


def _render_pending_deletions(console: Console, phase: dict[str, Any]) -> None:
    """Warn about documents the pending migrations are about to remove.

    Printed from the preflight section that was computed *before* the
    migrations ran, so on a real repair this is a warning rather than a
    post-mortem.
    """
    section: dict[str, Any] = phase.get("pending_deletions") or {}
    if not section:
        return
    total: int = section.get("total", 0)
    console.print(
        f"    [yellow]pending migrations remove {total} document(s)[/yellow]; "
        "copies are kept under .vault/.trash/"
    )
    items: list[str] = section.get("items", [])
    for item in items:
        console.print(f"      [red]-[/red] {item}")
    returned: int = section.get("returned", 0)
    if total > returned:
        console.print(f"      [dim]... and {total - returned} more[/dim]")


def _render_check_phase(
    console: Console, phase: dict[str, Any], *, verbose: bool
) -> None:
    errors = phase.get("error_count", 0)
    warnings = phase.get("warning_count", 0)
    fixed = phase.get("fixed_count", 0)
    summary = f"{errors} errors, {warnings} warnings"
    if fixed:
        summary += f", {fixed} fixed"
    if phase.get("dry_run"):
        summary += ", preview only"
    name = phase.get("phase", "unknown")
    console.print(f"  [bold]{name}[/bold]: {summary}")
    if verbose:
        _render_phase_diagnostics(console, phase)


def _render_index_phase(
    console: Console, phase: dict[str, Any], *, verbose: bool
) -> None:
    if phase.get("skipped"):
        console.print(f"  [bold]index[/bold]: skipped ({phase.get('reason')})")
        return
    if phase.get("dry_run"):
        paths = phase.get("planned", [])
        console.print(f"  [bold]index[/bold]: {len(paths)} planned")
    else:
        paths = phase.get("generated", [])
        console.print(f"  [bold]index[/bold]: {len(paths)} refreshed")
    if not verbose:
        return
    for path in paths:
        console.print(f"    {path}")


def _render_summary_phase(console: Console, phase: dict[str, Any]) -> None:
    changed = phase.get("changed_files", [])
    unresolved = phase.get("unresolved_count", 0)
    console.print(f"  [bold]summary[/bold]: {len(changed)} changed files")
    console.print(f"    unresolved diagnostics: {unresolved}")
    if phase.get("partial_failure"):
        console.print("    [red]partial failure: true[/red]")
    if phase.get("journal_count"):
        console.print(f"    journal entries: {phase['journal_count']}")


def _render_planned_fixes(console: Console, run: RepairRun) -> None:
    if not run.planned_fixes or not run.dry_run:
        return
    console.print()
    console.print(f"[bold]Planned mechanical fixes[/bold] ({len(run.planned_fixes)})")
    for item in run.planned_fixes[:_PLANNED_FIX_LIMIT]:
        path = f"{item['path']}: " if item.get("path") else ""
        console.print(f"  - {path}{item['fix_description'] or item['message']}")
    _render_elision(console, len(run.planned_fixes), _PLANNED_FIX_LIMIT, "more")


def _render_root_causes(console: Console, run: RepairRun) -> None:
    if not run.root_causes:
        return
    console.print()
    console.print("[bold]Root-cause groups[/bold]")
    for group in run.root_causes:
        console.print(f"  - {group['root_cause']}: {group['count']}")


def _render_changed_files(console: Console, run: RepairRun) -> None:
    if not run.changed_files:
        return
    console.print()
    console.print("[bold]Changed files[/bold]")
    for path in run.changed_files[:_CHANGED_FILE_LIMIT]:
        console.print(f"  - {path}")
    _render_elision(console, len(run.changed_files), _CHANGED_FILE_LIMIT, "more")


def _render_unresolved(console: Console, run: RepairRun, *, verbose: bool) -> None:
    if not run.unresolved:
        return
    console.print()
    console.print("[bold]Unresolved work[/bold]")
    severity_rank = {"error": 0, "warning": 1, "info": 2}
    display_items = [
        item for item in run.unresolved if verbose or item.get("severity") != "info"
    ]
    hidden_info = len(run.unresolved) - len(display_items)
    display_items.sort(key=lambda item: severity_rank.get(str(item.get("severity")), 3))
    for item in display_items[:_UNRESOLVED_LIMIT]:
        path = f"{item['path']}: " if item.get("path") else ""
        console.print(f"  - [{item['severity']}] {path}{item['message']}")
    if hidden_info:
        console.print(
            f"  ... {hidden_info} INFO diagnostics hidden; "
            "rerun with --verbose to show them."
        )
    _render_elision(
        console, len(display_items), _UNRESOLVED_LIMIT, "more non-INFO diagnostics"
    )


def _render_elision(console: Console, total: int, limit: int, noun: str) -> None:
    """Print the ``... N more`` tail when a section was truncated."""
    if total > limit:
        console.print(f"  ... {total - limit} {noun}")


def _render_phase_diagnostics(console: Console, phase: dict[str, Any]) -> None:
    for check in phase.get("checks", []):
        diagnostics = check.get("diagnostics", [])
        if not diagnostics:
            continue
        console.print(f"    {check['check_name']}:")
        for diag in diagnostics[:_DIAGNOSTIC_LIMIT]:
            path = f"{diag['path']}: " if diag.get("path") else ""
            console.print(f"      - [{diag['severity']}] {path}{diag['message']}")

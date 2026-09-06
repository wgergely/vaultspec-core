"""Operations backing ``vaultspec-core vault add``.

The ``add`` verb is the single ingress for scaffolding ``.vault/`` records, so
its Typer callback in :mod:`.vault_cmd` carries a wide option surface and a
long validate-resolve-scaffold-emit sequence. This module owns the sequence:
each helper validates or resolves one input, renders its own operator message,
and raises :class:`typer.Exit` on refusal, leaving the callback as the ordered
composition of those steps.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING, NoReturn

import typer

from vaultspec_core.cli.json_output import json_format_kwargs

if TYPE_CHECKING:
    from collections.abc import Generator, Mapping, Sequence
    from pathlib import Path

    from rich.console import Console

    from vaultspec_core.plan.parser import Plan, Step
    from vaultspec_core.vaultcore.exec_log import LogOutcome
    from vaultspec_core.vaultcore.models import DocType
    from vaultspec_core.vaultcore.query import VaultDocument

#: Plan tiers accepted by ``--tier``.
_PLAN_TIERS = frozenset({"L1", "L2", "L3", "L4"})


def fail(console: Console, message: str) -> NoReturn:
    """Render an operator error and exit with code 1."""
    console.print(f"[red]{message}[/red]")
    raise typer.Exit(code=1)


def resolve_doc_type(console: Console, doc_type: str) -> DocType:
    """Resolve the positional document-type argument to its enum member."""
    from vaultspec_core.vaultcore.models import DocType

    try:
        dt = DocType(doc_type)
    except ValueError:
        valid = ", ".join(d.value for d in DocType if d is not DocType.INDEX)
        console.print(
            f"[red]Unknown document type '{doc_type}'. Valid types: {valid}[/red]"
        )
        raise typer.Exit(code=1) from None
    if dt is DocType.INDEX:
        console.print(
            "[red]'index' documents are auto-generated. "
            "Use 'vaultspec-core vault feature index' instead of "
            "'vaultspec-core vault add index'.[/red]"
        )
        raise typer.Exit(code=1)
    if dt is DocType.EXEC:
        # Execution has one artifact, the plan's ledger, and one writer.
        # Refusing here, before any plan or template is resolved, keeps the
        # scaffolder from ever producing a per-Step record again.
        from vaultspec_core.vaultcore.hydration import EXEC_NOT_SCAFFOLDED

        console.print(f"[red]Error: {EXEC_NOT_SCAFFOLDED}.[/red]")
        raise typer.Exit(code=1)
    return dt


def validate_tier(console: Console, dt: DocType, tier: str) -> None:
    """Reject an out-of-range ``--tier`` value on a plan document."""
    from vaultspec_core.vaultcore.models import DocType

    if dt is DocType.PLAN and tier not in _PLAN_TIERS:
        fail(console, f"Invalid tier '{tier}'. Allowed values: L1, L2, L3, L4.")


def normalize_topic(console: Console, dt: DocType, topic: str | None) -> str | None:
    """Validate the narrative filename infix for the doc types that admit one.

    The topic is held to the same kebab-case discipline as the feature tag.
    """
    from vaultspec_core.vaultcore.models import DocType
    from vaultspec_core.vaultcore.normalize import normalize_feature_tag

    if topic is None:
        return None
    if dt not in (DocType.ADR, DocType.AUDIT, DocType.REFERENCE, DocType.RESEARCH):
        fail(
            console,
            "Error: --topic is only valid for 'adr', 'audit', 'reference', "
            "and 'research' documents.",
        )
    result = normalize_feature_tag(topic, label="topic")
    if not result.ok or result.value is None:
        fail(console, str(result.error))
    return result.value


def normalize_feature(console: Console, feature: str) -> str:
    """Validate the feature tag through the shared vaultcore normalizer.

    The one validator the MCP surface also converges on.
    """
    from vaultspec_core.vaultcore.normalize import normalize_feature_tag

    result = normalize_feature_tag(feature)
    if not result.ok or result.value is None:
        fail(console, str(result.error))
    return result.value


def resolve_date(console: Console, date: str | None) -> str:
    """Resolve ``--date`` to a canonical date token, defaulting to today.

    The flag is held to the same admission discipline as ``--feature`` and
    ``--topic``: the value is parsed into a calendar date and re-rendered
    from it, so a value that is not a date is refused here - before the
    scaffolder composes a filename from it - rather than reported as an
    advisory once the document is already on disk.

    Args:
        console: The console the failure is rendered to.
        date: The operator's ``--date`` value, or ``None`` for today.

    Returns:
        The canonical ``yyyy-mm-dd`` string.
    """
    from vaultspec_core.vaultcore.models import vault_today
    from vaultspec_core.vaultcore.normalize import normalize_vault_date

    if date is None:
        # Today on the vault's single canonical clock (UTC).
        return vault_today().isoformat()
    result = normalize_vault_date(date, label="--date value")
    if not result.ok or result.value is None:
        fail(console, str(result.error))
    return result.value


def normalize_extra_tags(console: Console, tags: list[str] | None) -> list[str] | None:
    """Validate additional ``--tags`` through the same shared normalizer."""
    from vaultspec_core.vaultcore.normalize import normalize_feature_tag

    if not tags:
        return None
    extra_tags: list[str] = []
    for tag in tags:
        result = normalize_feature_tag(tag, label="tag")
        if not result.ok:
            fail(console, str(result.error))
        extra_tags.append(f"#{result.value}")
    return extra_tags


def resolve_related(
    console: Console, related: list[str] | None, root_dir: Path
) -> list[str] | None:
    """Resolve ``--related`` inputs to ``[[wiki-link]]`` form."""
    from vaultspec_core.vaultcore.resolve import (
        RelatedResolutionError,
        resolve_related_inputs,
    )

    if not related:
        return None
    try:
        return resolve_related_inputs(related, root_dir)
    except RelatedResolutionError as exc:
        for failure in exc.failures:
            console.print(f"[red]Cannot resolve related document: '{failure}'[/red]")
        console.print(
            "[dim]Accepted formats: absolute path, relative path, "
            "filename, stem, or [[wiki-link]][/dim]"
        )
        raise typer.Exit(code=1) from None


def report_dependency_diagnostics(
    console: Console,
    root_dir: Path,
    dt: DocType,
    feature: str,
    *,
    json_output: bool,
) -> None:
    """Emit the feature-lifecycle diagnostics and stop on any hard error."""
    from vaultspec_core.vaultcore.resolve import validate_feature_dependencies

    diagnostics = validate_feature_dependencies(root_dir, dt, feature)
    errors = [d for d in diagnostics if d.startswith("ERROR:")]

    if json_output:
        _echo_dependency_json(diagnostics, errors)
    else:
        _print_dependency_text(console, diagnostics)

    if errors:
        raise typer.Exit(code=1)


def _print_dependency_text(console: Console, diagnostics: Sequence[str]) -> None:
    """Print every lifecycle diagnostic, errors in red and advisories in yellow."""
    for diag in diagnostics:
        style = "red" if diag.startswith("ERROR:") else "yellow"
        console.print(f"[{style}]{diag}[/{style}]")


def _echo_dependency_json(diagnostics: Sequence[str], errors: Sequence[str]) -> None:
    """Route advisories to stderr and any errors to the failure envelope."""
    for diag in diagnostics:
        if not diag.startswith("ERROR:"):
            typer.echo(diag, err=True)
    if not errors:
        return

    import json

    from vaultspec_core.cli.rendering import json_envelope

    typer.echo(
        json.dumps(
            json_envelope("vault.add", "failed", {"message": " ".join(errors)}),
            **json_format_kwargs(),
        )
    )


def resolve_parent_plan(
    console: Console,
    root_dir: Path,
    feature: str,
    resolved_related: list[str] | None,
) -> VaultDocument:
    """Resolve the plan document an execution record belongs to.

    An explicit ``--related`` stem wins; otherwise the feature must own
    exactly one plan.
    """
    from vaultspec_core.vaultcore.query import list_documents

    named = _plan_named_by_related(root_dir, resolved_related)
    if named is not None:
        return named

    plan_docs = list_documents(root_dir, doc_type="plan", feature=feature)
    if len(plan_docs) == 1:
        return plan_docs[0]
    if len(plan_docs) > 1:
        names = ", ".join(d.path.name for d in plan_docs)
        fail(
            console,
            f"Multiple plans found for feature '{feature}': {names}. "
            "Specify the parent plan using --related.",
        )
    fail(
        console,
        f"No plan found for feature '{feature}'. "
        "Create a plan document before logging execution.",
    )


def _plan_named_by_related(
    root_dir: Path, resolved_related: list[str] | None
) -> VaultDocument | None:
    """Return the first plan document named by a resolved wiki-link, if any."""
    from vaultspec_core.vaultcore.query import list_documents

    for rel in resolved_related or []:
        stem = rel.lstrip("[").rstrip("]")
        for doc in list_documents(root_dir, doc_type="plan"):
            if doc.path.stem == stem:
                return doc
    return None


def resolve_step_row(console: Console, plan: Plan, step: str) -> Step:
    """Resolve ``--step`` to one Step row of the parent plan."""
    from vaultspec_core.plan.commands.step_ops import (
        AmbiguousStepError,
        StepNotFoundError,
        find_step,
    )

    try:
        return find_step(plan, step)
    except (StepNotFoundError, AmbiguousStepError) as exc:
        console.print(f"[red]Error: {exc}[/red]")
        raise typer.Exit(code=1) from None


@contextmanager
def suppress_logging(*, active: bool) -> Generator[None]:
    """Silence library logging while a machine-readable payload is emitted."""
    import logging

    if not active:
        yield
        return
    previous = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        yield
    finally:
        logging.disable(previous)


def emit_add_result(
    console: Console,
    path: Path,
    doc_type: str,
    *,
    json_output: bool,
    dry_run: bool = False,
    hints: Mapping[str, object] | None = None,
) -> None:
    """Emit the created (or previewed) document as text or the JSON envelope."""
    if not json_output:
        label = "[dim]Would create:[/dim]" if dry_run else "[green]Created:[/green]"
        console.print(f"{label} {path}")
        return

    import json

    from vaultspec_core.cli.rendering import json_envelope

    data: dict[str, object] = {
        "path": str(path),
        "type": doc_type,
        "name": path.stem,
    }
    if dry_run:
        data["dry_run"] = True
    typer.echo(
        json.dumps(
            json_envelope("vault.add", "created", data, hints=hints),
            **json_format_kwargs(),
        )
    )


def parse_row_specs(
    console: Console, specs: Sequence[str]
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Validate ``--row`` specs into ledger row cells, refusing on the first bad one."""
    from vaultspec_core.vaultcore.exec_log import ExecLogError, parse_row_spec

    parsed: list[tuple[str, tuple[str, ...]]] = []
    for spec in specs:
        try:
            parsed.append(parse_row_spec(spec))
        except ExecLogError as exc:
            console.print(f"[red]Error:[/red] {exc}.")
            raise typer.Exit(code=1) from None
    return tuple(parsed)


def parse_verify(console: Console, spec: str | None) -> tuple[str, str] | None:
    """Validate the ``--verify`` spec, refusing a result other than pass or fail."""
    from vaultspec_core.vaultcore.exec_log import ExecLogError, parse_verify_spec

    if spec is None:
        return None
    try:
        return parse_verify_spec(spec)
    except ExecLogError as exc:
        console.print(f"[red]Error:[/red] {exc}.")
        raise typer.Exit(code=1) from None


def log_ledger_rows(
    console: Console,
    *,
    root_dir: Path,
    feature: str,
    plan_stem: str,
    step: str,
    rows: Sequence[tuple[str, tuple[str, ...]]],
    verify: tuple[str, str] | None = None,
    by: str | None = None,
    notes: Sequence[str] = (),
    dry_run: bool,
    json_output: bool,
) -> LogOutcome:
    """Append one Step's evidence to its plan's ledger through the shared core.

    Args:
        console: Console for operator messages.
        root_dir: Project root directory.
        feature: Feature tag, with or without a leading ``#``.
        plan_stem: Stem of the parent plan the ledger records.
        step: Canonical Step identifier or display path being logged.
        rows: Parsed ``(op, paths)`` pairs from :func:`parse_row_specs`.
        verify: ``(command, result)`` for the ``verify:`` row, if any.
        by: Persona for the ``by:`` row, if any.
        notes: Exception notes, one ``## Notes`` line each.
        dry_run: Resolve and report the target without writing.
        json_output: Suppress the human-readable confirmation line.

    Returns:
        The :class:`~vaultspec_core.vaultcore.exec_log.LogOutcome`.
    """
    from vaultspec_core.vaultcore.exec_log import ExecLogError, LogRequest, log_step

    request = LogRequest(
        feature=feature,
        plan_stem=plan_stem,
        step=step,
        rows=tuple(rows),
        verify=verify,
        by=by,
        notes=tuple(notes),
    )
    try:
        outcome = log_step(root_dir, request, dry_run=dry_run)
    except ExecLogError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from None

    if json_output:
        return outcome
    total = len(outcome.rows) + len(outcome.notes)
    if dry_run:
        console.print(f"[dim]Would log {total} row(s) to:[/dim] {outcome.path}")
    else:
        console.print(
            f"[green]Logged:[/green] {total} row(s) for "
            f"{outcome.step_id} -> {outcome.path.name}"
        )
    return outcome


def fold_exec_records(
    console: Console,
    *,
    root_dir: Path,
    feature: str,
    dry_run: bool,
    force: bool,
    json_output: bool,
) -> tuple[Path | None, object]:
    """Fold one feature's per-Step execution records into its plan's ledger.

    The fold is destructive - it removes the records whose content the
    ledger now carries - so it refuses to write without ``--force``, and
    reports exactly what it would do instead. What a dry run prints and what
    a forced run applies come from one planner, so the preview is the plan.

    Args:
        console: Console for operator messages.
        root_dir: Project root directory.
        feature: Feature tag, with or without a leading ``#``.
        dry_run: Report the plan without writing.
        force: Required to apply a destructive fold.
        json_output: Suppress human-readable lines.

    Returns:
        The ``(ledger_path, plan)`` pair; ``ledger_path`` is ``None`` when
        nothing was folded.

    Raises:
        typer.Exit: When the feature has no execution records, or when a
            non-dry run was requested without ``--force``.
    """
    from vaultspec_core.config import get_config
    from vaultspec_core.vaultcore.exec_fold import (
        apply_fold,
        collect_sources,
        phase_steps_of,
        plan_fold,
        sources_from,
        summarize,
    )

    feat = normalize_feature(console, feature)
    exec_root = root_dir / get_config().docs_dir / "exec"
    folders = sorted(p for p in exec_root.glob(f"*-{feat}") if p.is_dir())
    # A flat record from before Step-aware scaffolding sits beside the
    # folders; it folds into the feature's ledger like any other record.
    flat = sorted(p for p in exec_root.glob(f"*-{feat}-exec.md") if p.is_file())
    if not folders and not flat:
        console.print(
            f"[red]Error:[/red] no execution folder found for feature {feat!r}."
        )
        raise typer.Exit(code=1)

    candidates = [*(path for folder in folders for path in folder.glob("*.md")), *flat]
    records, plan_stem, covered = collect_sources(candidates)
    folder_name = (
        folders[0].name if folders else f"{(plan_stem or flat[0].stem)[:10]}-{feat}"
    )
    plan_stem = plan_stem or f"{folder_name}-plan"
    plan_path = root_dir / get_config().docs_dir / "plan" / f"{plan_stem}.md"

    plan = plan_fold(
        sources_from(records),
        phase_steps=phase_steps_of(plan_path),
        covered=covered,
    )
    if not json_output:
        console.print(summarize(plan, folder_name))
        for skip in plan.skipped:
            console.print(f"  [dim]skip[/dim] {skip.path.name} - {skip.reason}")

    if plan.is_empty:
        return None, plan

    if not force and not dry_run:
        console.print(
            "[yellow]Refusing to fold without --force:[/yellow] this removes "
            f"{len(plan.removed)} record(s). Re-run with --force to apply, or "
            "--dry-run to silence this."
        )
        raise typer.Exit(code=1)

    ledger_path = apply_fold(
        root_dir,
        plan,
        feature=feat,
        folder_date=folder_name[:10],
        plan_stem=plan_stem,
        dry_run=dry_run,
    )
    if not json_output:
        if dry_run:
            console.print(f"[dim]Would write:[/dim] {ledger_path}")
        else:
            console.print(
                f"[green]Folded:[/green] {len(plan.removed)} record(s) into "
                f"{ledger_path.name}"
            )
    return ledger_path, plan

"""Vault health-check and sanitize verbs.

Defines the ``vaultspec-core vault check ...`` subcommands (mounted on
:data:`vaultspec_core.cli.vault_cmd_app.check_app`) and the deprecated
``vaultspec-core vault sanitize annotations`` verb (mounted on
:data:`vaultspec_core.cli.vault_cmd_app.sanitize_app`). Split out of
:mod:`vaultspec_core.cli.vault_cmd` to keep that module under the project's
line-count ceiling; all commands re-export through ``vault_cmd`` so no
import site outside the package changes. All backend logic lives in
:mod:`vaultspec_core.vaultcore.checks`.

``vault repair`` used to live here too and now sits in
:mod:`vaultspec_core.cli.vault_cmd` beside the other ``vault_app`` commands.
It mounts on ``vault_app``, not on a sub-app, and ``vault_cmd`` registered it
*after* its own commands; importing this module at the top of ``vault_cmd``
would have registered it first instead, silently reordering ``vault --help``
and the generated command reference.

The commands decorate at module level rather than inside ``register_*(app)``
wrappers. Under the old wrappers each command was a closure nothing called,
which ``basedpyright`` reported as ``reportUnusedFunction`` and which was
answered by an inline ``# pyright: ignore`` on all 23 of them - suppressions
this project otherwise bans. Importing the apps from
:mod:`vaultspec_core.cli.vault_cmd_app` removes the import cycle the wrappers
existed to dodge, so the suppressions stop being necessary.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Any, cast

import typer

from vaultspec_core.cli._target import TargetOption, apply_target
from vaultspec_core.cli.json_output import json_format_kwargs
from vaultspec_core.cli.vault_cmd_app import check_app, sanitize_app
from vaultspec_core.core.windowing import windowed_section
from vaultspec_core.vaultcore.checks._base import DIAGNOSTIC_RENDER_CAP

if TYPE_CHECKING:
    from _typeshed import DataclassInstance

    from vaultspec_core.vaultcore.checks._base import CheckResult

__all__ = [
    "cmd_check_adr_status",
    "cmd_check_all",
    "cmd_check_annotations",
    "cmd_check_body_links",
    "cmd_check_body_sections",
    "cmd_check_code_boundary",
    "cmd_check_dangling",
    "cmd_check_encoding",
    "cmd_check_exec_mapping",
    "cmd_check_feature_rename_integrity",
    "cmd_check_features",
    "cmd_check_foreign",
    "cmd_check_frontmatter",
    "cmd_check_links",
    "cmd_check_markdown",
    "cmd_check_modified_stamp",
    "cmd_check_orphans",
    "cmd_check_placeholders",
    "cmd_check_references",
    "cmd_check_rename_integrity",
    "cmd_check_schema",
    "cmd_check_structure",
    "cmd_sanitize_annotations",
]


# ---- vault check subcommands ------------------------------------------------


def _reject_fix(check_name: str, fix: bool) -> None:
    """Error and exit if --fix is used on a check that doesn't support it."""
    if fix:
        from vaultspec_core.console import get_console

        console = get_console()
        console.print(
            f"[red]Error: 'vaultspec-core vault check {check_name}'"
            " has no auto-fix capabilities.[/red]"
        )
        raise typer.Exit(code=1)


def _check_status(results: list[CheckResult]) -> str:
    """Aggregate canonical outcome word for a set of check results.

    ``failed`` when any error is present, ``updated`` when ``--fix``
    corrected something, else ``unchanged``.
    """
    if any(r.error_count for r in results):
        return "failed"
    if any(r.fixed_count for r in results):
        return "updated"
    return "unchanged"


#: Shared paging options for the check verbs.
#:
#: A cap with no way past it converts a saturation failure into a workflow one:
#: an agent remediating a broken vault could see the first findings and had no
#: mechanism to reach the rest. Aggregate counts are never windowed, so
#: severity totals stay exact on any page.
LimitOption = Annotated[
    int | None, typer.Option("--limit", help="Maximum findings to return per check")
]
OffsetOption = Annotated[
    int, typer.Option("--offset", help="Findings to skip, for paging")
]


def _bounded_check_payload(
    result: object, *, limit: int | None = None, offset: int = 0
) -> dict[str, Any]:
    """Render one check result with its diagnostics bounded.

    ``dataclasses.asdict`` returned every finding, so the machine payload grew
    with how broken the vault was and was largest exactly when a caller could
    least afford it: measured 6,962 bytes clean, 137,323 at 5% of documents
    damaged, 2,211,057 fully damaged, while the human rendering converged at
    69,119 because it had a cap. Counts are untouched, so severity totals stay
    exact however many findings are withheld.

    Args:
        result: The check result to render.
        limit: Maximum findings to carry.
        offset: Findings to skip, for paging.

    Returns:
        The result mapping with ``diagnostics`` replaced by a window.
    """
    import dataclasses

    payload: dict[str, Any] = dataclasses.asdict(cast("DataclassInstance", result))
    diagnostics = payload.get("diagnostics")
    if isinstance(diagnostics, list):
        payload["diagnostics"] = windowed_section(
            diagnostics,  # pyright: ignore[reportUnknownArgumentType]
            limit=DIAGNOSTIC_RENDER_CAP if limit is None else limit,
            offset=offset,
        )
    return payload


def _render_and_exit(
    result: CheckResult,
    verbose: bool,
    json_output: bool = False,
    *,
    command: str,
    limit: int | None = None,
    offset: int = 0,
) -> None:
    """Render a CheckResult and exit with appropriate code."""
    if json_output:
        import json

        from vaultspec_core.cli.rendering import json_envelope

        envelope = json_envelope(
            command,
            _check_status([result]),
            _bounded_check_payload(result, limit=limit, offset=offset),
            version=2,
        )
        typer.echo(json.dumps(envelope, **json_format_kwargs(), default=str))
        raise typer.Exit(code=1 if result.error_count else 0)
    from vaultspec_core.console import get_console
    from vaultspec_core.vaultcore.checks import render_check_result

    console = get_console()
    render_check_result(console, result, verbose=verbose)
    if result.error_count:
        raise typer.Exit(code=1)


# ---- vault check subcommands ------------------------------------------------


@check_app.command("all")
def cmd_check_all(
    fix: Annotated[
        bool,
        typer.Option("--fix", help="Apply safe auto-corrections to vault content"),
    ] = False,
    feature: Annotated[
        str | None, typer.Option("--feature", "-f", help="Filter by feature tag")
    ] = None,
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Show INFO-level diagnostics")
    ] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    limit: LimitOption = None,
    offset: OffsetOption = 0,
    no_hints: Annotated[
        bool, typer.Option("--no-hints", help="Suppress next-step advisory hints")
    ] = False,
    target: TargetOption = None,
) -> None:
    """Run all vault health checks."""
    apply_target(target)
    from vaultspec_core.console import get_console
    from vaultspec_core.core.types import get_context as _get_ctx
    from vaultspec_core.vaultcore.checks import render_check_result, run_all_checks

    console = get_console()
    results = run_all_checks(_get_ctx().target_dir, feature=feature, fix=fix)

    if fix and sum(r.fixed_count for r in results) > 0:
        from vaultspec_core.cli._cache_hook import invalidate_graph_cache

        invalidate_graph_cache(_get_ctx().target_dir)

    total_errors = sum(r.error_count for r in results)
    outcome = "failed" if total_errors > 0 else "unchanged"

    from vaultspec_core.cli.rendering import emit_next_step_hint

    hint_dict = emit_next_step_hint(
        command="vault.check.all",
        outcome=outcome,
        json_output=json_output,
        no_hints=no_hints,
    )

    if json_output:
        import json

        from vaultspec_core.cli.rendering import json_envelope

        envelope = json_envelope(
            "vault.check.all",
            _check_status(results),
            {
                "checks": [
                    _bounded_check_payload(r, limit=limit, offset=offset)
                    for r in results
                ]
            },
            hints=hint_dict,
        )
        typer.echo(json.dumps(envelope, **json_format_kwargs(), default=str))
        raise typer.Exit(0 if total_errors == 0 else 1)

    console.print("[bold]Vault Check  - All[/bold]")
    for r in results:
        render_check_result(console, r, verbose=verbose)

    total_warnings = sum(r.warning_count for r in results)
    total_fixed = sum(r.fixed_count for r in results)

    console.print()
    parts: list[str] = []
    if total_errors:
        parts.append(
            f"[red]{total_errors} error{'s' if total_errors != 1 else ''}[/red]"
        )
    if total_warnings:
        sfx = "s" if total_warnings != 1 else ""
        parts.append(f"[yellow]{total_warnings} warning{sfx}[/yellow]")
    if total_fixed:
        parts.append(f"[green]{total_fixed} fixed[/green]")
    if parts:
        console.print(f"  Total: {', '.join(parts)}")
    else:
        console.print("  [green]All checks passed.[/green]")

    if total_errors:
        raise typer.Exit(code=1)


@check_app.command("body-links")
def cmd_check_body_links(
    fix: Annotated[
        bool,
        typer.Option("--fix", help="Convert body wiki-links to code spans"),
    ] = False,
    feature: Annotated[
        str | None, typer.Option("--feature", "-f", help="Filter by feature tag")
    ] = None,
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Show INFO-level diagnostics")
    ] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    limit: LimitOption = None,
    offset: OffsetOption = 0,
    target: TargetOption = None,
) -> None:
    """Find wiki-links and markdown path links in document body text."""
    apply_target(target)
    from vaultspec_core.core.types import get_context as _get_ctx
    from vaultspec_core.graph import VaultGraph
    from vaultspec_core.vaultcore.checks import check_body_links

    graph = VaultGraph(_get_ctx().target_dir)
    snapshot = graph.to_snapshot()
    result = check_body_links(
        _get_ctx().target_dir, snapshot=snapshot, feature=feature, fix=fix
    )
    _render_and_exit(
        result,
        verbose,
        json_output=json_output,
        limit=limit,
        offset=offset,
        command="vault.check.body-links",
    )


@check_app.command("exec-mapping")
def cmd_check_exec_mapping(
    feature: Annotated[
        str | None, typer.Option("--feature", "-f", help="Filter by feature tag")
    ] = None,
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Show INFO-level diagnostics")
    ] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    limit: LimitOption = None,
    offset: OffsetOption = 0,
    target: TargetOption = None,
) -> None:
    """Pair ledger rows with plan Steps and flag closed Steps without evidence."""
    apply_target(target)
    from vaultspec_core.core.types import get_context as _get_ctx
    from vaultspec_core.graph import VaultGraph
    from vaultspec_core.vaultcore.checks import check_exec_mapping

    snapshot = VaultGraph(_get_ctx().target_dir).to_snapshot()
    result = check_exec_mapping(
        _get_ctx().target_dir, snapshot=snapshot, feature=feature
    )
    _render_and_exit(
        result,
        verbose,
        json_output=json_output,
        limit=limit,
        offset=offset,
        command="vault.check.exec-mapping",
    )


@check_app.command("body-sections")
def cmd_check_body_sections(
    feature: Annotated[
        str | None, typer.Option("--feature", "-f", help="Filter by feature tag")
    ] = None,
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Show INFO-level diagnostics")
    ] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    limit: LimitOption = None,
    offset: OffsetOption = 0,
    target: TargetOption = None,
) -> None:
    """Check document bodies carry the sections their template mandates."""
    apply_target(target)
    from vaultspec_core.core.types import get_context as _get_ctx
    from vaultspec_core.graph import VaultGraph
    from vaultspec_core.vaultcore.checks import check_body_sections

    snapshot = VaultGraph(_get_ctx().target_dir).to_snapshot()
    result = check_body_sections(
        _get_ctx().target_dir, snapshot=snapshot, feature=feature
    )
    _render_and_exit(
        result,
        verbose,
        json_output=json_output,
        limit=limit,
        offset=offset,
        command="vault.check.body-sections",
    )


@check_app.command("annotations")
def cmd_check_annotations(
    fix: Annotated[
        bool,
        typer.Option("--fix", help="Strip generated template annotations"),
    ] = False,
    feature: Annotated[
        str | None, typer.Option("--feature", "-f", help="Filter by feature tag")
    ] = None,
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Show INFO-level diagnostics")
    ] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    limit: LimitOption = None,
    offset: OffsetOption = 0,
    target: TargetOption = None,
) -> None:
    """Find generated template annotations in vault documents."""
    apply_target(target)
    from vaultspec_core.core.types import get_context as _get_ctx
    from vaultspec_core.vaultcore.checks import check_annotations

    result = check_annotations(_get_ctx().target_dir, feature=feature, fix=fix)
    _render_and_exit(
        result,
        verbose,
        json_output=json_output,
        limit=limit,
        offset=offset,
        command="vault.check.annotations",
    )


@check_app.command("markdown")
def cmd_check_markdown(
    fix: Annotated[
        bool,
        typer.Option("--fix", help="Repair markdown hygiene issues"),
    ] = False,
    feature: Annotated[
        str | None, typer.Option("--feature", "-f", help="Filter by feature tag")
    ] = None,
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Show INFO-level diagnostics")
    ] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    limit: LimitOption = None,
    offset: OffsetOption = 0,
    target: TargetOption = None,
) -> None:
    """Check and optionally fix markdown hygiene (whitespace, blank runs, \
newline)."""
    apply_target(target)
    from vaultspec_core.core.types import get_context as _get_ctx
    from vaultspec_core.vaultcore.checks import check_markdown

    result = check_markdown(_get_ctx().target_dir, feature=feature, fix=fix)
    _render_and_exit(
        result,
        verbose,
        json_output=json_output,
        limit=limit,
        offset=offset,
        command="vault.check.markdown",
    )


@check_app.command("placeholders")
def cmd_check_placeholders(
    feature: Annotated[
        str | None, typer.Option("--feature", "-f", help="Filter by feature tag")
    ] = None,
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Show INFO-level diagnostics")
    ] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    limit: LimitOption = None,
    offset: OffsetOption = 0,
    target: TargetOption = None,
) -> None:
    """Find unreplaced {...} template placeholders in document body prose."""
    apply_target(target)
    from vaultspec_core.core.types import get_context as _get_ctx
    from vaultspec_core.graph import VaultGraph
    from vaultspec_core.vaultcore.checks import check_placeholders

    graph = VaultGraph(_get_ctx().target_dir)
    snapshot = graph.to_snapshot()
    result = check_placeholders(
        _get_ctx().target_dir, snapshot=snapshot, feature=feature
    )
    _render_and_exit(
        result,
        verbose,
        json_output=json_output,
        limit=limit,
        offset=offset,
        command="vault.check.placeholders",
    )


@check_app.command("dangling")
def cmd_check_dangling(
    fix: Annotated[
        bool,
        typer.Option("--fix", help="Apply safe auto-corrections to vault content"),
    ] = False,
    feature: Annotated[
        str | None, typer.Option("--feature", "-f", help="Filter by feature tag")
    ] = None,
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Show INFO-level diagnostics")
    ] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    limit: LimitOption = None,
    offset: OffsetOption = 0,
    target: TargetOption = None,
) -> None:
    """Find wiki-links in related: frontmatter that resolve to no document."""
    apply_target(target)
    from vaultspec_core.core.types import get_context as _get_ctx
    from vaultspec_core.graph import VaultGraph
    from vaultspec_core.vaultcore.checks import check_dangling

    graph = VaultGraph(_get_ctx().target_dir)
    result = check_dangling(
        _get_ctx().target_dir, graph=graph, feature=feature, fix=fix
    )
    _render_and_exit(
        result,
        verbose,
        json_output=json_output,
        limit=limit,
        offset=offset,
        command="vault.check.dangling",
    )


@check_app.command("orphans")
def cmd_check_orphans(
    fix: Annotated[
        bool,
        typer.Option("--fix", help="Apply safe auto-corrections to vault content"),
    ] = False,
    feature: Annotated[
        str | None, typer.Option("--feature", "-f", help="Filter by feature tag")
    ] = None,
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Show INFO-level diagnostics")
    ] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    limit: LimitOption = None,
    offset: OffsetOption = 0,
    target: TargetOption = None,
) -> None:
    """Find documents with no incoming wiki-links."""
    apply_target(target)
    _reject_fix("orphans", fix)
    from vaultspec_core.core.types import get_context as _get_ctx
    from vaultspec_core.graph import VaultGraph
    from vaultspec_core.vaultcore.checks import check_orphans

    graph = VaultGraph(_get_ctx().target_dir)
    result = check_orphans(_get_ctx().target_dir, graph=graph, feature=feature)
    _render_and_exit(
        result,
        verbose,
        json_output=json_output,
        limit=limit,
        offset=offset,
        command="vault.check.orphans",
    )


@check_app.command("frontmatter")
def cmd_check_frontmatter(
    fix: Annotated[
        bool,
        typer.Option("--fix", help="Apply safe auto-corrections to vault content"),
    ] = False,
    feature: Annotated[
        str | None, typer.Option("--feature", "-f", help="Filter by feature tag")
    ] = None,
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Show INFO-level diagnostics")
    ] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    limit: LimitOption = None,
    offset: OffsetOption = 0,
    target: TargetOption = None,
) -> None:
    """Validate document frontmatter against vault schema."""
    apply_target(target)
    from vaultspec_core.core.types import get_context as _get_ctx
    from vaultspec_core.graph import VaultGraph
    from vaultspec_core.vaultcore.checks import check_frontmatter

    graph = VaultGraph(_get_ctx().target_dir)
    snapshot = graph.to_snapshot()
    result = check_frontmatter(
        _get_ctx().target_dir, snapshot=snapshot, feature=feature, fix=fix
    )
    _render_and_exit(
        result,
        verbose,
        json_output=json_output,
        limit=limit,
        offset=offset,
        command="vault.check.frontmatter",
    )


@check_app.command("modified-stamp")
def cmd_check_modified_stamp(
    fix: Annotated[
        bool,
        typer.Option("--fix", help="Apply safe auto-corrections to vault content"),
    ] = False,
    feature: Annotated[
        str | None, typer.Option("--feature", "-f", help="Filter by feature tag")
    ] = None,
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Show INFO-level diagnostics")
    ] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    limit: LimitOption = None,
    offset: OffsetOption = 0,
    target: TargetOption = None,
) -> None:
    """Validate and reconcile the modified recency stamp on every document."""
    apply_target(target)
    from vaultspec_core.core.types import get_context as _get_ctx
    from vaultspec_core.graph import VaultGraph
    from vaultspec_core.vaultcore.checks import check_modified_stamp

    graph = VaultGraph(_get_ctx().target_dir)
    snapshot = graph.to_snapshot()
    result = check_modified_stamp(
        _get_ctx().target_dir, snapshot=snapshot, feature=feature, fix=fix
    )
    _render_and_exit(
        result,
        verbose,
        json_output=json_output,
        limit=limit,
        offset=offset,
        command="vault.check.modified-stamp",
    )


@check_app.command("links")
def cmd_check_links(
    fix: Annotated[
        bool,
        typer.Option("--fix", help="Apply safe auto-corrections to vault content"),
    ] = False,
    feature: Annotated[
        str | None, typer.Option("--feature", "-f", help="Filter by feature tag")
    ] = None,
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Show INFO-level diagnostics")
    ] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    limit: LimitOption = None,
    offset: OffsetOption = 0,
    target: TargetOption = None,
) -> None:
    """Check wiki-links follow Obsidian convention (no .md extension)."""
    apply_target(target)
    from vaultspec_core.core.types import get_context as _get_ctx
    from vaultspec_core.graph import VaultGraph
    from vaultspec_core.vaultcore.checks import check_links

    graph = VaultGraph(_get_ctx().target_dir)
    snapshot = graph.to_snapshot()
    result = check_links(
        _get_ctx().target_dir, snapshot=snapshot, feature=feature, fix=fix
    )
    _render_and_exit(
        result,
        verbose,
        json_output=json_output,
        limit=limit,
        offset=offset,
        command="vault.check.links",
    )


@check_app.command("features")
def cmd_check_features(
    fix: Annotated[
        bool,
        typer.Option("--fix", help="Apply safe auto-corrections to vault content"),
    ] = False,
    feature: Annotated[
        str | None, typer.Option("--feature", "-f", help="Filter by feature tag")
    ] = None,
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Show INFO-level diagnostics")
    ] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    limit: LimitOption = None,
    offset: OffsetOption = 0,
    target: TargetOption = None,
) -> None:
    """Check feature tag completeness  - missing doc types."""
    apply_target(target)
    _reject_fix("features", fix)
    from vaultspec_core.core.types import get_context as _get_ctx
    from vaultspec_core.graph import VaultGraph
    from vaultspec_core.vaultcore.checks import check_features

    graph = VaultGraph(_get_ctx().target_dir)
    snapshot = graph.to_snapshot()
    result = check_features(_get_ctx().target_dir, snapshot=snapshot, feature=feature)
    _render_and_exit(
        result,
        verbose,
        json_output=json_output,
        limit=limit,
        offset=offset,
        command="vault.check.features",
    )


@check_app.command("references")
def cmd_check_references(
    fix: Annotated[
        bool,
        typer.Option("--fix", help="Apply safe auto-corrections to vault content"),
    ] = False,
    feature: Annotated[
        str | None, typer.Option("--feature", "-f", help="Filter by feature tag")
    ] = None,
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Show INFO-level diagnostics")
    ] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    limit: LimitOption = None,
    offset: OffsetOption = 0,
    target: TargetOption = None,
) -> None:
    """Check for missing cross-references within features."""
    apply_target(target)
    from vaultspec_core.core.types import get_context as _get_ctx
    from vaultspec_core.graph import VaultGraph
    from vaultspec_core.vaultcore.checks import check_references

    graph = VaultGraph(_get_ctx().target_dir)
    result = check_references(
        _get_ctx().target_dir, graph=graph, feature=feature, fix=fix
    )
    _render_and_exit(
        result,
        verbose,
        json_output=json_output,
        limit=limit,
        offset=offset,
        command="vault.check.references",
    )


@check_app.command("schema")
def cmd_check_schema(
    fix: Annotated[
        bool,
        typer.Option("--fix", help="Apply safe auto-corrections to vault content"),
    ] = False,
    feature: Annotated[
        str | None, typer.Option("--feature", "-f", help="Filter by feature tag")
    ] = None,
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Show INFO-level diagnostics")
    ] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    limit: LimitOption = None,
    offset: OffsetOption = 0,
    target: TargetOption = None,
) -> None:
    """Enforce schema rules: ADRs must ref research, plans must ref ADRs."""
    apply_target(target)
    from vaultspec_core.core.types import get_context as _get_ctx
    from vaultspec_core.graph import VaultGraph
    from vaultspec_core.vaultcore.checks import check_schema

    graph = VaultGraph(_get_ctx().target_dir)
    result = check_schema(_get_ctx().target_dir, graph=graph, feature=feature, fix=fix)
    _render_and_exit(
        result,
        verbose,
        json_output=json_output,
        limit=limit,
        offset=offset,
        command="vault.check.schema",
    )


@check_app.command("adr-status")
def cmd_check_adr_status(
    fix: Annotated[
        bool,
        typer.Option("--fix", help="Apply safe auto-corrections to vault content"),
    ] = False,
    feature: Annotated[
        str | None, typer.Option("--feature", "-f", help="Filter by feature tag")
    ] = None,
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Show INFO-level diagnostics")
    ] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    limit: LimitOption = None,
    offset: OffsetOption = 0,
    target: TargetOption = None,
) -> None:
    """Validate ADR status against the canonical taxonomy."""
    apply_target(target)
    from vaultspec_core.core.types import get_context as _get_ctx
    from vaultspec_core.graph import VaultGraph
    from vaultspec_core.vaultcore.checks import check_adr_status

    graph = VaultGraph(_get_ctx().target_dir)
    snapshot = graph.to_snapshot()
    result = check_adr_status(
        _get_ctx().target_dir, snapshot=snapshot, feature=feature, fix=fix
    )
    _render_and_exit(
        result,
        verbose,
        json_output=json_output,
        limit=limit,
        offset=offset,
        command="vault.check.adr-status",
    )


@check_app.command("code-boundary")
def cmd_check_code_boundary(
    feature: Annotated[
        str | None,
        typer.Option(
            "--feature",
            "-f",
            help="Restrict the scanned record stems to one feature's documents",
        ),
    ] = None,
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Show INFO-level diagnostics")
    ] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    limit: LimitOption = None,
    offset: OffsetOption = 0,
    target: TargetOption = None,
) -> None:
    """Scan source files for references to the project's own vault records.

    Opt-in and advisory: findings are warnings, the exit code stays zero,
    and nothing is mutated. Not part of `vaultspec-core vault check all`.
    """
    apply_target(target)
    from vaultspec_core.core.types import get_context as _get_ctx
    from vaultspec_core.vaultcore.checks import check_code_boundary

    result = check_code_boundary(_get_ctx().target_dir, feature=feature)
    _render_and_exit(
        result,
        verbose,
        json_output=json_output,
        limit=limit,
        offset=offset,
        command="vault.check.code-boundary",
    )


@check_app.command("structure")
def cmd_check_structure(
    fix: Annotated[
        bool,
        typer.Option("--fix", help="Apply safe auto-corrections to vault content"),
    ] = False,
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Show INFO-level diagnostics")
    ] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    limit: LimitOption = None,
    offset: OffsetOption = 0,
    target: TargetOption = None,
) -> None:
    """Check vault directory structure and filename conventions."""
    apply_target(target)
    from vaultspec_core.core.types import get_context as _get_ctx
    from vaultspec_core.graph import VaultGraph
    from vaultspec_core.vaultcore.checks import check_structure

    graph = VaultGraph(_get_ctx().target_dir)
    snapshot = graph.to_snapshot()
    result = check_structure(_get_ctx().target_dir, snapshot=snapshot, fix=fix)
    _render_and_exit(
        result,
        verbose,
        json_output=json_output,
        limit=limit,
        offset=offset,
        command="vault.check.structure",
    )


@check_app.command("rename-integrity")
def cmd_check_rename_integrity(
    fix: Annotated[
        bool,
        typer.Option(
            "--fix", help="Filename-wins: update frontmatter name to match filename"
        ),
    ] = False,
    fix_frontmatter_wins: Annotated[
        bool,
        typer.Option(
            "--fix-frontmatter-wins",
            help=("Frontmatter-wins: physically rename file to match frontmatter name"),
        ),
    ] = False,
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Show INFO-level diagnostics")
    ] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    limit: LimitOption = None,
    offset: OffsetOption = 0,
    target: TargetOption = None,
) -> None:
    """Check name/filename integrity for rules, skills, and agents."""
    apply_target(target)
    from vaultspec_core.core.types import get_context as _get_ctx
    from vaultspec_core.vaultcore.checks import check_rename_integrity

    root_dir = _get_ctx().target_dir

    def confirm_fn(prompt: str) -> bool:
        return typer.confirm(prompt, default=True)

    result = check_rename_integrity(
        root_dir,
        fix=fix,
        fix_frontmatter_wins=fix_frontmatter_wins,
        confirm_fn=confirm_fn if not json_output else None,
    )
    _render_and_exit(
        result,
        verbose,
        json_output=json_output,
        limit=limit,
        offset=offset,
        command="vault.check.rename-integrity",
    )


@check_app.command("encoding")
def cmd_check_encoding(
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Show INFO-level diagnostics")
    ] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    limit: LimitOption = None,
    offset: OffsetOption = 0,
    target: TargetOption = None,
) -> None:
    """Surface .vault/ documents that are not valid UTF-8 (detection only).

    Encoding is validated vault-wide and takes no ``--feature`` filter: a
    non-UTF-8 document has no parseable feature tag to scope by.
    """
    apply_target(target)
    from vaultspec_core.core.types import get_context as _get_ctx
    from vaultspec_core.vaultcore.checks import check_encoding

    result = check_encoding(_get_ctx().target_dir)
    _render_and_exit(
        result,
        verbose,
        json_output=json_output,
        limit=limit,
        offset=offset,
        command="vault.check.encoding",
    )


@check_app.command("feature-rename-integrity")
def cmd_check_feature_rename_integrity(
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Show INFO-level diagnostics")
    ] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    limit: LimitOption = None,
    offset: OffsetOption = 0,
    target: TargetOption = None,
) -> None:
    """Surface exec folders whose feature disagrees with their records' tag.

    Detection only: it reports post-rename drift between an exec folder name
    and the ``#feature`` tag of the records inside it. It is vault-wide and
    takes no ``--feature`` filter; index/staleness defer to ``check_features``
    and filename/directory grammar to ``check_structure``.
    """
    apply_target(target)
    from vaultspec_core.core.types import get_context as _get_ctx
    from vaultspec_core.vaultcore.checks import check_feature_rename_integrity

    result = check_feature_rename_integrity(_get_ctx().target_dir)
    _render_and_exit(
        result,
        verbose,
        json_output=json_output,
        limit=limit,
        offset=offset,
        command="vault.check.feature-rename-integrity",
    )


@check_app.command("foreign")
def cmd_check_foreign(
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Show INFO-level diagnostics")
    ] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    limit: LimitOption = None,
    offset: OffsetOption = 0,
    target: TargetOption = None,
) -> None:
    """Warn about files the framework did not place inside managed roots.

    Detection only, vault-wide, and takes no ``--feature``: a foreign file
    has no vault frontmatter to carry a feature tag in the first place.
    """
    apply_target(target)
    from vaultspec_core.core.types import get_context as _get_ctx
    from vaultspec_core.vaultcore.checks import check_foreign

    result = check_foreign(_get_ctx().target_dir)
    _render_and_exit(
        result,
        verbose,
        json_output=json_output,
        limit=limit,
        offset=offset,
        command="vault.check.foreign",
    )


@sanitize_app.command("annotations")
def cmd_sanitize_annotations(
    feature: Annotated[
        str | None, typer.Option("--feature", "-f", help="Filter by feature tag")
    ] = None,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Preview annotation stripping")
    ] = False,
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Show stripped files")
    ] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    limit: LimitOption = None,
    offset: OffsetOption = 0,
    target: TargetOption = None,
) -> None:
    """Strip generated template annotations from vault documents."""
    apply_target(target)
    from vaultspec_core.core.types import get_context as _get_ctx
    from vaultspec_core.vaultcore.checks import check_annotations

    if not json_output:
        from vaultspec_core.console import get_console

        console = get_console()
        console.print(
            "[yellow]Deprecation Warning: "
            "'vaultspec-core vault sanitize annotations' is deprecated. "
            "Please use 'vaultspec-core vault check annotations --fix' "
            "instead.[/yellow]"
        )

    result = check_annotations(
        _get_ctx().target_dir, feature=feature, fix=True, dry_run=dry_run
    )
    if not dry_run and result.fixed_count > 0:
        from vaultspec_core.cli._cache_hook import invalidate_graph_cache

        invalidate_graph_cache(_get_ctx().target_dir)
    _render_and_exit(
        result,
        verbose or dry_run,
        json_output=json_output,
        limit=limit,
        offset=offset,
        command="vault.sanitize.annotations",
    )

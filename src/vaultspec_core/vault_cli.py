"""Implement the `.vault/` command group for vault document workflows.

This module is the user-facing CLI adapter over vault document scaffolding,
verification, graph analysis, metrics, and hook execution. It exposes the
commands used to create new `.vault/` records and to audit existing vault
content from the command line.

Usage:
    Use the `vault` Typer app through the root CLI, especially the `add` and
    `audit` commands for document creation and vault analysis.
"""

import json
import logging
from datetime import datetime
from typing import Annotated

import typer

from .graph import VaultGraph
from .metrics import get_vault_metrics
from .vaultcore import (
    DocType,
    create_vault_doc,
)
from .verification import (
    fix_violations,
    get_malformed,
    list_features,
    verify_vertical_integrity,
)

logger = logging.getLogger(__name__)

app = typer.Typer(
    help="Create and audit records in the .vault project history.",
    no_args_is_help=False,
)


@app.callback(invoke_without_command=True)
def vault_main(ctx: typer.Context):
    """Vault command group callback."""
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit(0)


@app.command("add")
def handle_create(
    ctx: typer.Context,
    type_str: Annotated[str, typer.Option("--type", help="Type of doc to create.")],
    feature: Annotated[
        str, typer.Option("--feature", help="Feature name (kebab-case).")
    ],
    title: Annotated[
        str | None, typer.Option("--title", help="Title of the document.")
    ] = None,
):
    """Create a new .vault/ document from a template."""
    target_dir = ctx.obj["target"]
    try:
        doc_type = DocType(type_str)
    except ValueError:
        logger.error("Error: Invalid doc type.")
        raise typer.Exit(1) from None

    feature = feature.strip("#")
    date_str = datetime.now().strftime("%Y-%m-%d")
    try:
        doc_path = create_vault_doc(target_dir, doc_type, feature, date_str, title)
    except FileNotFoundError as exc:
        logger.error("Error: %s", exc)
        raise typer.Exit(1) from exc
    except FileExistsError as exc:
        logger.error("Error: %s", exc)
        raise typer.Exit(1) from exc

    from .hooks import fire_hooks

    fire_hooks(
        "vault.document.created",
        {
            "path": str(doc_path),
            "root": str(target_dir),
            "event": "vault.document.created",
        },
    )


@app.command("audit")
def handle_audit(
    ctx: typer.Context,
    summary: bool = typer.Option(False, "--summary", help="Show summary stats."),
    features: bool = typer.Option(False, "--features", help="List all features."),
    verify: bool = typer.Option(False, "--verify", help="Run full verification."),
    graph: bool = typer.Option(False, "--graph", help="Show graph hotspots."),
    limit: int = typer.Option(10, "--limit", help="Limit number of items in reports."),
    type_filter: str = typer.Option(None, "--type", help="Filter hotspots by DocType."),
    feature: str = typer.Option(
        None, "--feature", help="Filter hotspots by feature tag."
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Output results in JSON format."
    ),
    fix: bool = typer.Option(False, "--fix", help="Auto-repair common violations."),
):
    """Run one or more audit operations on the .vault/ directory."""
    if fix:
        verify = True

    from rich import box
    from rich.panel import Panel
    from rich.table import Table

    from vaultspec_core.console import get_console

    console = get_console()
    root_dir = ctx.obj["target"]
    results = {}

    if summary:
        metrics = get_vault_metrics(root_dir)
        results["summary"] = {
            "total_docs": metrics.total_docs,
            "total_features": metrics.total_features,
            "counts_by_type": {
                dt.value: count for dt, count in metrics.counts_by_type.items()
            },
        }
        if not json_output:
            kv = Table(box=None, show_header=False, padding=(0, 1))
            kv.add_column("k", style="dim")
            kv.add_column("v")
            kv.add_row("Total Documents:", str(metrics.total_docs))
            kv.add_row("Total Features:", str(metrics.total_features))
            for dt_val, count in results["summary"]["counts_by_type"].items():
                kv.add_row(f"  {dt_val}:", str(count))
            console.print(Panel(kv, title="Vault Summary"))
            console.print()

    if features:
        features_list = list_features(root_dir)
        results["features"] = sorted(features_list)
        if not json_output:
            console.print(f"[bold]Features ({len(features_list)}):[/bold]")
            for f in results["features"]:
                console.print(f"  [dim]-[/dim] {f}")
            console.print()

    if verify:
        errors = get_malformed(root_dir)
        errors.extend(verify_vertical_integrity(root_dir))

        results["verification"] = {
            "passed": len(errors) == 0,
            "errors": [{"path": str(e.path), "message": e.message} for e in errors],
        }
        if not json_output:
            if errors:
                console.print(
                    f"[bold red]Verification Failed ({len(errors)} errors):[/bold red]"
                )
                for err in errors:
                    console.print(f"  {err}")
            else:
                console.print("[bold green]Verification Passed.[/bold green]")
            console.print()

        if fix and errors:
            if not json_output:
                console.print("[bold]Running auto-repair...[/bold]")
            fixes = fix_violations(root_dir)
            results["fixes"] = [
                {
                    "path": str(f.path),
                    "action": f.action,
                    "detail": f.detail,
                }
                for f in fixes
            ]
            if not json_output:
                if fixes:
                    console.print(f"\n[bold]Applied {len(fixes)} fixes:[/bold]")
                    for f in fixes:
                        console.print(f"  {f}")
                else:
                    console.print("\nNo auto-fixable violations found.")
                console.print()

    if graph:
        try:
            vault_graph = VaultGraph(root_dir)
            doc_type_filter = DocType(type_filter) if type_filter else None

            hotspots = vault_graph.get_hotspots(
                limit=limit, doc_type=doc_type_filter, feature=feature
            )

            graph_results: dict[str, object] = {
                "hotspots": [{"name": name, "count": count} for name, count in hotspots]
            }
            results["graph"] = graph_results

            if not json_output:
                title = "Graph Hotspots"
                if doc_type_filter:
                    title += f" (Type: {doc_type_filter.value})"
                if feature:
                    title += f" (Feature: {feature})"
                hotspot_table = Table(
                    box=box.SIMPLE_HEAD, highlight=False, show_edge=False, title=title
                )
                hotspot_table.add_column("Document", no_wrap=True)
                hotspot_table.add_column("Incoming Links", justify="right")
                for name, count in hotspots:
                    hotspot_table.add_row(name, str(count))
                console.print(hotspot_table)

            if not type_filter and not feature:
                f_rankings = vault_graph.get_feature_rankings(limit=limit)
                graph_results["feature_rankings"] = [
                    {"feature": f, "count": c} for f, c in f_rankings
                ]
                if not json_output:
                    feat_table = Table(
                        box=box.SIMPLE_HEAD,
                        highlight=False,
                        show_edge=False,
                        title="Hottest Features (Cumulative Links)",
                    )
                    feat_table.add_column("Feature", no_wrap=True)
                    feat_table.add_column("Total Incoming Links", justify="right")
                    for f_name, count in f_rankings:
                        feat_table.add_row(f_name, str(count))
                    console.print(feat_table)

            invalid = vault_graph.get_invalid_links()
            graph_results["invalid_links"] = [
                {"source": s, "target": t} for s, t in invalid
            ]
            if not json_output and invalid:
                console.print(
                    f"\n[bold yellow]Invalid Links ({len(invalid)}):[/bold yellow]"
                )
                for source, t_target in invalid:
                    console.print(
                        f"  {source} [dim]->[/dim] [[{t_target}]] (Target not found)"
                    )

            orphans = vault_graph.get_orphaned()
            graph_results["orphans"] = orphans
            if not json_output and orphans:
                console.print(
                    f"\n[bold yellow]Orphaned Documents ({len(orphans)}):[/bold yellow]"
                )
                for name in orphans:
                    console.print(f"  [dim]-[/dim] {name}")
                console.print()
        except Exception as e:
            logger.error("Graph analysis failed: %s", e, exc_info=True)

    if json_output:
        typer.echo(json.dumps(results))

    from .hooks import fire_hooks

    fire_hooks("audit.completed", {"root": str(root_dir), "event": "audit.completed"})

"""Vault command group -- manage .vault/ documentation records.

Provides commands for creating, querying, and auditing vault documents.
Delegates to the vaultcore query engine and hydration module for backend logic.
"""

from __future__ import annotations

import logging
from typing import Annotated

import typer

logger = logging.getLogger(__name__)

vault_app = typer.Typer(
    help="Create, query, and audit records in the .vault/ project history.",
    no_args_is_help=True,
)

feature_app = typer.Typer(
    help="Manage vault feature tags.",
    no_args_is_help=True,
)
vault_app.add_typer(feature_app, name="feature")


# ---- vault add ---------------------------------------------------------------


@vault_app.command("add")
def cmd_add(
    doc_type: Annotated[str, typer.Argument(help="Document type to create")],
    feature: Annotated[
        str, typer.Option("--feature", "-f", help="Feature tag (kebab-case)")
    ] = "",
    date: Annotated[
        str | None, typer.Option("--date", help="Override date (YYYY-MM-DD)")
    ] = None,
    title: Annotated[str | None, typer.Option("--title", help="Document title")] = None,
    content: Annotated[
        str | None, typer.Option("--content", help="Initial content")
    ] = None,
) -> None:
    """Create a new .vault/ document from a template."""
    from datetime import datetime

    from vaultspec_core.console import get_console
    from vaultspec_core.core import types as _t
    from vaultspec_core.vaultcore.hydration import create_vault_doc
    from vaultspec_core.vaultcore.models import DocType

    console = get_console()

    # Resolve doc type enum
    try:
        dt = DocType(doc_type)
    except ValueError:
        valid = ", ".join(d.value for d in DocType)
        console.print(
            f"[red]Unknown document type '{doc_type}'. Valid types: {valid}[/red]"
        )
        raise typer.Exit(code=1) from None

    # Default date to today
    date_str = date or datetime.now().strftime("%Y-%m-%d")

    try:
        path = create_vault_doc(
            root_dir=_t.TARGET_DIR,
            doc_type=dt,
            feature=feature.lstrip("#"),
            date_str=date_str,
            title=title,
        )
        console.print(f"[green]Created:[/green] {path}")
    except FileNotFoundError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from None
    except FileExistsError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from None


# ---- vault stats -------------------------------------------------------------


@vault_app.command("stats")
def cmd_stats(
    feature: Annotated[
        str | None, typer.Option("--feature", "-f", help="Filter by feature tag")
    ] = None,
    date: Annotated[
        str | None, typer.Option("--date", help="Filter by date (YYYY-MM-DD)")
    ] = None,
    type_filter: Annotated[
        str | None, typer.Option("--type", help="Filter by document type")
    ] = None,
    invalid: Annotated[
        bool, typer.Option("--invalid", help="Show only invalid documents")
    ] = False,
    orphaned: Annotated[
        bool, typer.Option("--orphaned", help="Show only orphaned documents")
    ] = False,
) -> None:
    """Show vault statistics and metrics."""
    from vaultspec_core.console import get_console
    from vaultspec_core.core import types as _t
    from vaultspec_core.vaultcore.query import get_stats

    stats = get_stats(_t.TARGET_DIR, feature=feature, doc_type=type_filter, date=date)
    console = get_console()
    console.print("[bold]Vault Statistics[/bold]")
    console.print(f"  Total documents: {stats['total_docs']}")
    console.print(f"  Total features:  {stats['total_features']}")
    if stats["counts_by_type"]:
        console.print("  By type:")
        for dt, count in sorted(stats["counts_by_type"].items()):
            console.print(f"    {dt}: {count}")
    if orphaned or invalid:
        if orphaned:
            console.print(f"  Orphaned docs: {stats['orphaned_count']}")
        if invalid:
            console.print(f"  Invalid links: {stats['invalid_link_count']}")


# ---- vault list --------------------------------------------------------------


@vault_app.command("list")
def cmd_list(
    doc_type: Annotated[
        str | None, typer.Argument(help="Document type to list")
    ] = None,
    date: Annotated[
        str | None, typer.Option("--date", help="Filter by date (YYYY-MM-DD)")
    ] = None,
    feature: Annotated[
        str | None, typer.Option("--feature", "-f", help="Filter by feature tag")
    ] = None,
) -> None:
    """List vault documents, optionally filtered by type."""
    from vaultspec_core.console import get_console
    from vaultspec_core.core import types as _t
    from vaultspec_core.vaultcore.query import list_documents

    docs = list_documents(_t.TARGET_DIR, doc_type=doc_type, feature=feature, date=date)
    console = get_console()
    if not docs:
        console.print("[dim]No documents found.[/dim]")
        return
    for d in docs:
        parts = [f"[bold]{d.name}[/bold]"]
        parts.append(f"[dim]{d.doc_type}[/dim]")
        if d.feature:
            parts.append(f"#{d.feature}")
        if d.date:
            parts.append(d.date)
        console.print("  ".join(parts))


# ---- vault doctor ------------------------------------------------------------


@vault_app.command("doctor")
def cmd_doctor() -> None:
    """Check vault health and integrity."""
    from vaultspec_core.console import get_console
    from vaultspec_core.core import types as _t
    from vaultspec_core.vaultcore.query import get_stats

    console = get_console()
    stats = get_stats(_t.TARGET_DIR)
    console.print("[bold]Vault Health Check[/bold]")
    console.print(f"  Documents: {stats['total_docs']}")
    console.print(f"  Features:  {stats['total_features']}")

    issues = []
    if stats["orphaned_count"] > 0:
        issues.append(
            f"{stats['orphaned_count']} orphaned documents (no incoming links)"
        )
    if stats["invalid_link_count"] > 0:
        issues.append(
            f"{stats['invalid_link_count']} invalid links (broken references)"
        )

    if issues:
        console.print("[yellow]Issues found:[/yellow]")
        for issue in issues:
            console.print(f"  [yellow]![/yellow] {issue}")
    else:
        console.print("[green]No issues found.[/green]")


# ---- vault feature list ------------------------------------------------------


@feature_app.command("list")
def cmd_feature_list(
    date: Annotated[str | None, typer.Option("--date", help="Filter by date")] = None,
    orphaned: Annotated[
        bool, typer.Option("--orphaned", help="Show only orphaned features")
    ] = False,
    type_filter: Annotated[
        str | None, typer.Option("--type", help="Filter by document type")
    ] = None,
) -> None:
    """List all feature tags in the vault."""
    from vaultspec_core.console import get_console
    from vaultspec_core.core import types as _t
    from vaultspec_core.vaultcore.query import list_feature_details

    features = list_feature_details(
        _t.TARGET_DIR, date=date, doc_type=type_filter, orphaned_only=orphaned
    )
    console = get_console()
    if not features:
        console.print("[dim]No features found.[/dim]")
        return
    for f in features:
        types_str = ", ".join(f["types"])
        plan_marker = " [green]plan[/green]" if f["has_plan"] else ""
        name = f["name"]
        count = f["doc_count"]
        console.print(
            f"  [bold]{name}[/bold]  {count} docs  ({types_str}){plan_marker}"
        )


# ---- vault feature archive ---------------------------------------------------


@feature_app.command("archive")
def cmd_feature_archive(
    feature_tag: Annotated[str, typer.Argument(help="Feature tag to archive")],
) -> None:
    """Archive all documents for a feature tag."""
    from vaultspec_core.console import get_console
    from vaultspec_core.core import types as _t
    from vaultspec_core.vaultcore.query import archive_feature

    result = archive_feature(_t.TARGET_DIR, feature_tag)
    console = get_console()
    if result["archived_count"] == 0:
        console.print(f"[dim]No documents found for feature '{feature_tag}'.[/dim]")
    else:
        console.print(f"[green]Archived {result['archived_count']} documents.[/green]")
        for p in result["paths"]:
            console.print(f"  {p}")

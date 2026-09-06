"""Vault command group  - create, query, graph, check, and audit ``.vault/`` records.

Sub-groups: ``vaultspec-core vault feature`` (:data:`feature_app`) and
``vaultspec-core vault check`` (:data:`check_app`). Delegates to
:mod:`vaultspec_core.vaultcore.query`, :mod:`vaultspec_core.vaultcore.hydration`,
:mod:`vaultspec_core.vaultcore.checks`, and :mod:`vaultspec_core.graph` for
all backend logic. Mounted onto :data:`.root.app` as the ``vault`` command group.

This module is the public surface: every command re-exports through it so no
import site outside the package changes. The ``vault check`` and
``vault sanitize`` verbs live in :mod:`vaultspec_core.cli.vault_check_cmd`, the
``vault feature`` verbs in :mod:`vaultspec_core.cli.vault_feature_cmd`, and the
document-editing verbs in :mod:`vaultspec_core.cli.edit_cmd`. Each decorates
the apps owned by :mod:`vaultspec_core.cli.vault_cmd_app` at module level, and
is imported here for that registration side effect - the same arrangement
:mod:`vaultspec_core.cli.plan_cmd` uses for its family.

``vault repair`` is defined in this module rather than beside the check verbs:
it mounts on :data:`vault_app` rather than on a sub-app, and it must register
after this module's own commands to keep its position in ``vault --help`` and
in the generated command reference.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, cast

import typer

from vaultspec_core.cli._errors import handle_error as _handle_error
from vaultspec_core.cli._target import TargetOption, apply_target

# Each sibling command module decorates the apps owned by `.vault_cmd_app` as
# an import-time side effect; importing its command names here, in definition
# order, both triggers that registration and reproduces the original --help
# listing order regardless of how ruff would otherwise sort these imports. The
# names are re-exported (via `__all__`) for call sites that imported them
# directly from this module, exactly as `.plan_cmd` does for its family.
#
# Deleting one of these imports would silently delete its commands from the
# CLI, because registration is now an import-time side effect rather than an
# explicit `register_*(app)` call. Two things stop that: the names are in
# `__all__`, so ruff will not autofix them away as unused, and
# `tests/cli/test_cli_reference_generated.py` fails, because the committed
# reference no longer matches what the generator produces from the live tree.
# Note it is that byte-fidelity test that catches a *disappearance* - the
# companion `test_cli_reference_drift.py` asserts coverage (every live command
# is documented), which a shrunken CLI still satisfies.
#
# One consequence of registering by import: the order above is the order ruff
# sorts these module names into, which today happens to match the order the
# old explicit `register_*(app)` calls used. A new sibling module whose name
# sorts differently would therefore re-order `vault --help`.
#
# That order is contractual, and it is already enforced - no separate test is
# needed for it. `reference_gen` renders the command inventory in registration
# order deliberately ("registration order (not alphabetical) is preserved"),
# and `tests/cli/test_cli_reference_generated.py` byte-compares the committed
# reference against fresh generator output. So a re-order fails CI even when
# the command set is identical: moving one command ahead of another, changing
# nothing else, fails four tests in that module. Verified by doing exactly
# that and watching them fail.
#
# The practical consequence for a contributor adding a sibling module: if the
# import sort lands it somewhere that shifts the listing, CI will say so, and
# the fix is to regenerate the reference (`vaultspec-core spec reference
# generate`) and commit it - accepting the new order - or to place the import
# so the old order holds. What cannot happen is the listing changing silently.
#
# The imports sit at module level rather than at the bottom of the file behind
# an E402 exemption: with `vault_cmd_app` owning the apps there is no longer a
# cycle back through this module to break.
from vaultspec_core.cli.edit_cmd import (
    cmd_edit,
    cmd_rename,
    cmd_set_body,
    cmd_set_frontmatter,
)
from vaultspec_core.cli.json_output import json_format_kwargs
from vaultspec_core.cli.vault_check_cmd import (
    cmd_check_adr_status,
    cmd_check_all,
    cmd_check_annotations,
    cmd_check_body_links,
    cmd_check_body_sections,
    cmd_check_code_boundary,
    cmd_check_dangling,
    cmd_check_encoding,
    cmd_check_exec_mapping,
    cmd_check_feature_rename_integrity,
    cmd_check_features,
    cmd_check_frontmatter,
    cmd_check_links,
    cmd_check_markdown,
    cmd_check_modified_stamp,
    cmd_check_orphans,
    cmd_check_placeholders,
    cmd_check_references,
    cmd_check_rename_integrity,
    cmd_check_schema,
    cmd_check_structure,
    cmd_sanitize_annotations,
)
from vaultspec_core.cli.vault_cmd_app import (
    adr_app,
    check_app,
    feature_app,
    rule_app,
    sanitize_app,
    vault_app,
)
from vaultspec_core.cli.vault_feature_cmd import (
    cmd_feature_archive,
    cmd_feature_index,
    cmd_feature_list,
    cmd_feature_rename,
    cmd_feature_unarchive,
)
from vaultspec_core.core.windowing import apply_window

# Every name this module exports, which is also - deliberately - every
# side-effecting import above. Pruning an entry here does not merely narrow the
# export surface: it frees ruff to remove the import, which unregisters that
# module's commands. The module's own commands are listed too, so this reads as
# a complete export list rather than an asymmetric one a reader might "tidy".
__all__ = [
    "adr_app",
    "check_app",
    "cmd_add",
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
    "cmd_edit",
    "cmd_feature_archive",
    "cmd_feature_index",
    "cmd_feature_list",
    "cmd_feature_rename",
    "cmd_feature_unarchive",
    "cmd_graph",
    "cmd_list",
    "cmd_rename",
    "cmd_repair",
    "cmd_sanitize_annotations",
    "cmd_set_body",
    "cmd_set_frontmatter",
    "cmd_stats",
    "feature_app",
    "rule_app",
    "sanitize_app",
    "vault_app",
]

if TYPE_CHECKING:
    from pathlib import Path

    from _typeshed import DataclassInstance
    from rich.console import Console

    from vaultspec_core.graph.api import VaultGraph


# The apps themselves live in `vault_cmd_app` so the per-verb command modules
# can mount onto them without importing back through this module. They are
# re-exported here because this module is the family's public surface.

from vaultspec_core.cli.plan_cmd import plan_app

vault_app.add_typer(plan_app, name="plan")

from vaultspec_core.cli.link_cmd import link_app  # noqa: E402

vault_app.add_typer(link_app, name="link")

from vaultspec_core.cli.exec_cmd import exec_app  # noqa: E402

vault_app.add_typer(exec_app, name="exec")

from vaultspec_core.cli.archive_cmd import archive_app  # noqa: E402

vault_app.add_typer(archive_app, name="archive")


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
    topic: Annotated[
        str | None,
        typer.Option(
            "--topic",
            help=(
                "Narrative filename infix (kebab-case) disambiguating a "
                "second document of the same type for a feature; produces "
                "{date}-{feature}-{topic}-{type}.md. Only valid for adr, audit, "
                "reference, and research documents."
            ),
        ),
    ] = None,
    related: Annotated[
        list[str] | None,
        typer.Option(
            "--related",
            "-r",
            help=(
                "Related document(s). Accepts absolute path, relative path, "
                "filename, or stem. Resolved to [[wiki-link]] format."
            ),
        ),
    ] = None,
    tags: Annotated[
        list[str] | None,
        typer.Option(
            "--tags",
            help="Required directory or feature tags only; other tags are rejected",
        ),
    ] = None,
    force: Annotated[
        bool, typer.Option("--force", help="Overwrite existing document")
    ] = False,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Preview without writing")
    ] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    no_hints: Annotated[
        bool, typer.Option("--no-hints", help="Suppress next-step advisory hints")
    ] = False,
    tier: Annotated[
        str,
        typer.Option(
            "--tier",
            help=(
                "Plan tier (L1..L4). Default L1. Ignored for non-plan "
                "document types whose templates do not carry a tier field."
            ),
        ),
    ] = "L1",
    target: TargetOption = None,
) -> None:
    """Create a new .vault/ document from a template.

    Supported types: adr, audit, plan, reference, research. Execution is not
    scaffolded: it is logged with ``vaultspec-core vault exec log``.
    """
    apply_target(target)
    from vaultspec_core.cli import _add_ops
    from vaultspec_core.console import get_console
    from vaultspec_core.core.types import get_context as _get_ctx
    from vaultspec_core.vaultcore.hydration import (
        DocumentIdentity,
        TemplateFields,
        WritePolicy,
        create_vault_doc,
    )
    from vaultspec_core.vaultcore.models import DocType

    console = get_console()
    root_dir = _get_ctx().target_dir

    dt = _add_ops.resolve_doc_type(console, doc_type)
    _add_ops.validate_tier(console, dt, tier)
    topic_value = _add_ops.normalize_topic(console, dt, topic)
    feat = _add_ops.normalize_feature(console, feature)
    date_str = _add_ops.resolve_date(console, date)
    extra_tags = _add_ops.normalize_extra_tags(console, tags)
    resolved_related = _add_ops.resolve_related(console, related, root_dir)
    _add_ops.report_dependency_diagnostics(
        console, root_dir, dt, feat, json_output=json_output
    )

    identity = DocumentIdentity(
        doc_type=dt, feature=feat, date=date_str, topic=topic_value
    )
    fields = TemplateFields(
        title=title,
        related=resolved_related,
        extra_tags=extra_tags,
        tier=tier if dt is DocType.PLAN else None,
    )
    write = WritePolicy(force=force, dry_run=dry_run)

    with _add_ops.suppress_logging(active=json_output):
        try:
            path = create_vault_doc(root_dir, identity, fields, write=write)
        except Exception as exc:
            _handle_error(exc, json_output=json_output)
            return

    if dry_run:
        _add_ops.emit_add_result(
            console, path, doc_type, json_output=json_output, dry_run=True
        )
        raise typer.Exit(0)

    # Reaching here means create_vault_doc wrote the document: exceptions above
    # cause an early return and a dry-run preview already exited.
    from vaultspec_core.cli._cache_hook import invalidate_graph_cache

    invalidate_graph_cache(root_dir)

    # Post-creation self-validation
    _validate_created_doc(console, path)

    from vaultspec_core.cli.rendering import emit_next_step_hint

    context_vars = {
        "feature": feat,
        "research_stem": path.stem,
        "adr_stem": path.stem,
        "plan_stem": path.stem,
        "audit_stem": path.stem,
        "rule_name": f"{feat}-rule",
    }

    hint_dict = emit_next_step_hint(
        command=f"vault.add.{dt.value}",
        outcome="created",
        context_vars=context_vars,
        json_output=json_output,
        no_hints=no_hints,
    )

    _add_ops.emit_add_result(
        console, path, doc_type, json_output=json_output, hints=hint_dict
    )
    if json_output:
        raise typer.Exit(0)


def _validate_created_doc(console: Console, doc_path: Path) -> None:
    """Run frontmatter validation on a newly created document.

    Prints warnings if the created document fails the project's own
    linting standards but does not block creation.
    """
    from vaultspec_core.vaultcore.parser import parse_vault_metadata

    try:
        content = doc_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return

    metadata, _ = parse_vault_metadata(content)
    errors = metadata.validate()
    if errors:
        console.print("[yellow]Post-creation validation warnings:[/yellow]")
        for err in errors:
            console.print(f"  [yellow]{err}[/yellow]")


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
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    target: TargetOption = None,
) -> None:
    """Show vault statistics and metrics."""
    apply_target(target)
    from vaultspec_core.console import get_console
    from vaultspec_core.core.types import get_context as _get_ctx
    from vaultspec_core.vaultcore.query import get_stats

    console = get_console()
    try:
        stats = get_stats(
            _get_ctx().target_dir, feature=feature, doc_type=type_filter, date=date
        )
    except OSError as exc:
        console.print(f"[red]Error reading vault: {exc}[/red]")
        raise typer.Exit(code=1) from exc
    if json_output:
        import json

        from vaultspec_core.cli.rendering import json_envelope

        typer.echo(
            json.dumps(
                json_envelope("vault.stats", "unchanged", stats),
                **json_format_kwargs(),
                default=str,
            )
        )
        raise typer.Exit(0)
    from vaultspec_core.cli.rendering import (
        Column,
        Field,
        render_listing,
        render_record,
        summary_line,
    )

    fields = [
        Field("total documents", str(stats["total_docs"])),
        Field("total features", str(stats["total_features"])),
    ]
    if orphaned:
        fields.append(Field("orphaned docs", str(stats["orphaned_count"])))
    if invalid:
        fields.append(Field("dangling links", str(stats["dangling_link_count"])))
    render_record(fields, title="Vault statistics")

    by_type = sorted(stats["counts_by_type"].items())
    if by_type:
        render_listing(
            [{"type": dt, "count": str(count)} for dt, count in by_type],
            [Column("type"), Column("count")],
            title="By type",
            summary=summary_line(sum(count for _, count in by_type), "documents"),
        )


# ---- vault list --------------------------------------------------------------


def _list_row(doc: object) -> dict[str, object]:
    """Project one document into the listing row.

    Drops what the caller can derive. Measured over 1,222 documents, 41% of the
    payload was recoverable: the absolute workspace prefix repeated on every
    row, ``name`` which is the path's stem, and ``tags`` which restate
    ``doc_type`` and ``feature`` already present as fields. Paths are emitted
    relative to the vault, whose root the envelope's caller already supplied.

    Args:
        doc: The document record to project.

    Returns:
        The row mapping.
    """
    import dataclasses

    from vaultspec_core.core.types import get_context as _get_ctx

    row: dict[str, object] = dataclasses.asdict(cast("DataclassInstance", doc))
    row.pop("name", None)
    row.pop("tags", None)
    # `asdict` leaves a Path as a Path, so guarding on `str` alone silently
    # skips every row and the absolute path ships anyway via `default=str`.
    raw = row.get("path")
    if raw is not None:
        text = str(raw)
        root = str(_get_ctx().target_dir)
        row["path"] = (
            text[len(root) :].lstrip(r"\/").replace("\\", "/")
            if text.startswith(root)
            else text
        )
    return row


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
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    limit: Annotated[
        int | None,
        typer.Option("--limit", help="Maximum documents to return"),
    ] = None,
    offset: Annotated[
        int, typer.Option("--offset", help="Documents to skip, for paging")
    ] = 0,
    target: TargetOption = None,
) -> None:
    """List vault documents, optionally filtered by type."""
    apply_target(target)
    from vaultspec_core.console import get_console
    from vaultspec_core.core.types import get_context as _get_ctx
    from vaultspec_core.vaultcore.models import DocType
    from vaultspec_core.vaultcore.query import list_documents

    console = get_console()

    # Validate doc_type and give helpful suggestions
    valid_types = {dt.value for dt in DocType} | {"orphaned", "invalid"}
    if doc_type and doc_type not in valid_types:
        if doc_type in ("features", "feature"):
            console.print(
                f"[yellow]'{doc_type}' is not a document type. "
                "Use [bold]vaultspec-core vault feature list[/bold] "
                "to list features.[/yellow]"
            )
            raise typer.Exit(code=1)
        console.print(
            f"[red]Unknown document type '{doc_type}'.[/red]\n"
            f"  Valid types: {', '.join(sorted(valid_types))}"
        )
        raise typer.Exit(code=1)

    try:
        docs = list_documents(
            _get_ctx().target_dir, doc_type=doc_type, feature=feature, date=date
        )
    except OSError as exc:
        console.print(f"[red]Error reading vault: {exc}[/red]")
        raise typer.Exit(code=1) from exc
    if json_output:
        import json

        from vaultspec_core.cli.rendering import json_envelope

        # A full-corpus dump was 5,934,666 bytes at 10,476 documents, and the
        # only narrowing available was an exact feature or date. The window is
        # applied here rather than in the renderer so the caller learns the
        # total it was cut from and how to page, instead of discovering the
        # truncation by surprise.
        page, window = apply_window(docs, limit=limit, offset=offset)
        payload: dict[str, object] = {
            "documents": [_list_row(d) for d in page],
        }
        payload.update(window.as_fields())
        typer.echo(
            json.dumps(
                json_envelope("vault.list", "unchanged", payload, version=2),
                **json_format_kwargs(),
                default=str,
            )
        )
        raise typer.Exit(0)
    from vaultspec_core.cli.rendering import (
        Cell,
        Column,
        render_listing,
        summary_line,
    )

    rows = [
        {
            "name": Cell(d.name, "bold"),
            "type": Cell(d.doc_type, "dim"),
            "feature": f"#{d.feature}" if d.feature else "",
            "date": d.date or "",
        }
        for d in docs
    ]
    render_listing(
        rows,
        [Column("name"), Column("type"), Column("feature"), Column("date")],
        title="Vault documents",
        summary=summary_line(len(docs), "documents"),
        empty="no documents found",
    )


# ---- vault graph ------------------------------------------------------------


@vault_app.command("graph")
def cmd_graph(
    feature: Annotated[
        str | None,
        typer.Option(
            "--feature",
            "-f",
            help="Scope to a single feature",
        ),
    ] = None,
    as_json: Annotated[
        bool,
        typer.Option("--json", help="Output graph as JSON"),
    ] = False,
    metrics: Annotated[
        bool,
        typer.Option("--metrics", "-m", help="Show metrics"),
    ] = False,
    ascii_graph: Annotated[
        bool,
        typer.Option(
            "--ascii",
            help="Render graph topology via phart",
        ),
    ] = False,
    include_body: Annotated[
        bool,
        typer.Option("--body", help="Include body in JSON"),
    ] = False,
    node: Annotated[
        str | None,
        typer.Option(
            "--node",
            help="Scope the JSON graph to this node's local (ego) neighbourhood",
        ),
    ] = None,
    depth: Annotated[
        int,
        typer.Option(
            "--depth",
            help="Ego-graph radius in hops; only used with --node",
        ),
    ] = 1,
    derived: Annotated[
        bool,
        typer.Option(
            "--derived/--no-derived",
            help=(
                "Include the derived relatedness edge set in JSON output "
                "(opt-in: it is a computed similarity ranking, not vault state)"
            ),
        ),
    ] = False,
    derived_limit: Annotated[
        int | None,
        typer.Option("--derived-limit", help="Maximum derived edges to return"),
    ] = None,
    derived_offset: Annotated[
        int, typer.Option("--derived-offset", help="Derived edges to skip, for paging")
    ] = 0,
    ref: Annotated[
        str | None,
        typer.Option(
            "--ref",
            help=(
                "Read the vault corpus from this git ref (branch/tag/sha) via "
                "the object database, without a working-tree checkout"
            ),
        ),
    ] = None,
    target: TargetOption = None,
) -> None:
    """Render the vault document graph.

    Default output is a Rich hierarchical tree grouped by feature and
    type.  Use --ascii for a phart ASCII topology rendering, --json
    for networkx node-link JSON export, or --metrics for aggregate
    statistics computed by networkx algorithms.

    For JSON output, --node <stem> with --depth N scopes the payload to a
    node's local (ego) neighbourhood, and --no-derived omits the derived
    relatedness edge set.

    Use --ref <branch|sha> to read the corpus from the git object database at
    that ref instead of the working tree (read-only; no checkout, no cache
    write). The JSON envelope stays ``vaultspec.vault.graph.v2`` with a
    top-level ``ref`` key naming the snapshot. A non-git workspace or an
    unresolvable ref fails with a typed error rather than a working-tree read.
    """
    apply_target(target)
    from vaultspec_core.console import get_console
    from vaultspec_core.core.types import get_context as _get_ctx
    from vaultspec_core.graph import VaultGraph
    from vaultspec_core.graph.refscan import RefScanError

    console = get_console()
    try:
        if ref is not None:
            graph = VaultGraph.from_ref(_get_ctx().target_dir, ref)
        else:
            graph = VaultGraph(_get_ctx().target_dir)
    except RefScanError as exc:
        console.print(f"[red]Error reading ref {ref!r}: {exc}[/red]")
        raise typer.Exit(code=1) from exc
    except OSError as exc:
        console.print(f"[red]Error reading vault: {exc}[/red]")
        raise typer.Exit(code=1) from exc

    if as_json and metrics:
        # Projection before format. `--metrics` asks for the summary, so it must
        # narrow the payload on every surface: it previously had no effect at all
        # in JSON mode, because this branch returned before the metrics branch
        # was reached. Measured, `vault graph --metrics --json` returned
        # 11,175,730 bytes where the human form of the same flag returned 4,794 -
        # a 2,331x penalty for asking the narrower question, with nothing telling
        # the caller their flag had been discarded.
        import json

        from vaultspec_core.cli.rendering import json_envelope

        typer.echo(
            json.dumps(
                json_envelope(
                    "vault.graph",
                    "unchanged",
                    {"metrics": graph.metrics(feature=feature)},
                    version=2,
                ),
                **json_format_kwargs(),
                default=str,
            )
        )
        return

    if as_json:
        import json

        from vaultspec_core.cli.rendering import json_envelope

        if node is not None and node not in graph.nodes:
            typer.echo(
                json.dumps(
                    json_envelope(
                        "vault.graph",
                        "failed",
                        {"message": f"Node not found: {node}"},
                        version=2,
                    ),
                    **json_format_kwargs(),
                    default=str,
                )
            )
            raise typer.Exit(code=1)

        envelope = json_envelope(
            "vault.graph",
            "unchanged",
            graph.to_dict(
                feature=feature,
                include_body=include_body,
                node=node,
                depth=depth,
                include_derived=derived,
                derived_limit=derived_limit,
                derived_offset=derived_offset,
            ),
            version=2,
        )
        typer.echo(json.dumps(envelope, **json_format_kwargs(), default=str))
        return

    if not graph.nodes:
        console.print("[dim]No vault documents found.[/dim]")
        raise typer.Exit(code=0)

    if metrics:
        _print_metrics(graph, feature=feature)
        return

    if ascii_graph:
        console.print(graph.render_ascii(feature=feature))
        return

    # Default: box-free hierarchical tree (renders directly).
    graph.render_tree(feature=feature)


def _print_metrics(
    graph: VaultGraph,
    feature: str | None = None,
) -> None:
    """Render graph metrics through the box-free Record and Listing shapes."""
    from vaultspec_core.cli.rendering import Field, render_record

    m = graph.metrics(feature=feature)

    title = f"Graph metrics - #{feature}" if feature else "Graph metrics"

    fields = [
        Field("documents", str(m.total_nodes)),
        Field("edges", str(m.total_edges)),
        Field("features", str(m.total_features)),
        Field("total_words", f"{m.total_words:,}"),
        Field("density", f"{m.density:.4f}"),
        Field("avg_in_degree", f"{m.avg_in_degree:.2f}"),
        Field("avg_out_degree", f"{m.avg_out_degree:.2f}"),
    ]
    if m.max_in_degree[1]:
        n, c = m.max_in_degree
        fields.append(Field("max_in_degree", f"{c} ({n})"))
    if m.max_out_degree[1]:
        n, c = m.max_out_degree
        fields.append(Field("max_out_degree", f"{c} ({n})"))
    fields += [
        Field("orphans", str(m.orphan_count)),
        Field("phantoms", str(m.phantom_count)),
        Field("dangling_links", str(m.dangling_link_count)),
        Field("components", str(m.connected_components)),
    ]

    render_record(fields, title=title)

    from vaultspec_core.cli.rendering import Column, render_listing, summary_line

    if m.nodes_by_type:
        render_listing(
            [{"type": dt, "count": str(c)} for dt, c in m.nodes_by_type.items()],
            [Column("type"), Column("count")],
            title="By type",
            summary=summary_line(sum(m.nodes_by_type.values()), "documents"),
        )

    if m.nodes_by_feature and not feature:
        render_listing(
            [
                {"feature": f"#{f}", "count": str(c)}
                for f, c in m.nodes_by_feature.items()
            ],
            [Column("feature"), Column("count")],
            title="By feature",
            summary=summary_line(len(m.nodes_by_feature), "features"),
        )

    if m.in_degree_centrality:
        render_listing(
            [
                {"document": n, "score": f"{s:.4f}"}
                for n, s in m.in_degree_centrality.items()
            ],
            [Column("document"), Column("score")],
            title="In-degree centrality (top 10)",
        )

    if m.betweenness_centrality:
        render_listing(
            [
                {"document": n, "score": f"{s:.4f}"}
                for n, s in m.betweenness_centrality.items()
            ],
            [Column("document"), Column("score")],
            title="Betweenness centrality (top 10)",
        )


# ---- vault repair -------------------------------------------------------


@vault_app.command("repair")
def cmd_repair(
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Preview repair actions without writing"),
    ] = False,
    include_index: Annotated[
        bool,
        typer.Option(
            "--include-index/--no-index",
            help="Refresh generated feature indexes during repair",
        ),
    ] = True,
    feature: Annotated[
        str | None,
        typer.Option("--feature", "-f", help="Scope repair to one feature tag"),
    ] = None,
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Show INFO-level diagnostics")
    ] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    target: TargetOption = None,
) -> None:
    """Run the operator repair pipeline for vault content.

    The repair pipeline is broader than ``vaultspec-core vault check all --fix``: it
    reports preflight and migration state, runs checks, applies safe
    check-level fixes unless ``--dry-run`` is set, refreshes generated
    feature indexes unless ``--no-index`` is set, rebuilds graph state,
    and runs a postcheck pass.
    """
    apply_target(target)
    from vaultspec_core.core.types import get_context as _get_ctx
    from vaultspec_core.vaultcore.repair import run_repair_pipeline

    run = run_repair_pipeline(
        _get_ctx().target_dir,
        dry_run=dry_run,
        include_index=include_index,
        feature=feature,
    )
    if not dry_run and run.changed_files:
        from vaultspec_core.cli._cache_hook import invalidate_graph_cache

        invalidate_graph_cache(_get_ctx().target_dir)
    if json_output:
        import json

        from vaultspec_core.cli._repair_render import repair_payload
        from vaultspec_core.cli.rendering import json_envelope

        if run.error_count:
            repair_status = "failed"
        elif run.fixed_count:
            repair_status = "updated"
        else:
            repair_status = "unchanged"
        typer.echo(
            json.dumps(
                json_envelope(
                    "vault.repair",
                    repair_status,
                    repair_payload(run),
                    version=2,
                ),
                **json_format_kwargs(),
                default=str,
            )
        )
        raise typer.Exit(code=1 if run.error_count else 0)

    from vaultspec_core.cli._repair_render import render_repair_run

    render_repair_run(run, verbose=verbose)
    if run.error_count:
        raise typer.Exit(code=1)


# ---- vault rule promote ------------------------------------------------------


@rule_app.command("promote")
def cmd_rule_promote(
    from_audit: Annotated[
        str, typer.Option("--from", help="Audit stem to promote from")
    ],
    as_rule: Annotated[
        str, typer.Option("--as", help="Kebab-case name of the promoted rule")
    ],
    force: Annotated[
        bool, typer.Option("--force", help="Overwrite existing rule source")
    ] = False,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Preview without writing")
    ] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    target: TargetOption = None,
) -> None:
    """Promote an audit finding to a team-shared rule."""
    apply_target(target)
    import json

    from vaultspec_core.cli.rendering import json_envelope
    from vaultspec_core.console import get_console
    from vaultspec_core.core.exceptions import VaultSpecError
    from vaultspec_core.core.rules import rule_promote

    try:
        rule_file = rule_promote(
            from_audit=from_audit,
            rule_name=as_rule,
            force=force,
            dry_run=dry_run,
        )
    except (VaultSpecError, OSError) as exc:
        _handle_error(exc, json_output=json_output)
        return

    console = get_console()
    if json_output:
        status = "created" if not dry_run else "unchanged"
        typer.echo(
            json.dumps(
                json_envelope(
                    "vault.rule.promote",
                    status,
                    {"path": str(rule_file)},
                ),
                **json_format_kwargs(),
            )
        )
        raise typer.Exit(0)

    action = "Would promote rule" if dry_run else "Rule promoted successfully"
    console.print(f"[green]{action}:[/green] {rule_file}")


# ---- vault adr supersede -----------------------------------------------------


@adr_app.command("supersede")
def cmd_adr_supersede(
    old_adr: Annotated[str, typer.Argument(help="Old ADR stem to supersede")],
    by_new_adr: Annotated[
        str,
        typer.Option(
            "--by",
            help="New ADR stem that supersedes the old one",
        ),
    ] = "",
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Preview without writing")
    ] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    target: TargetOption = None,
) -> None:
    """Supersede an old ADR with a new ADR."""
    apply_target(target)
    import json

    from vaultspec_core.cli.rendering import json_envelope
    from vaultspec_core.console import get_console
    from vaultspec_core.core.adr import adr_supersede
    from vaultspec_core.core.exceptions import VaultSpecError

    console = get_console()

    if not by_new_adr:
        if json_output:
            typer.echo(
                json.dumps(
                    json_envelope(
                        "vault.adr.supersede",
                        "failed",
                        {"message": "--by option is required."},
                    ),
                    **json_format_kwargs(),
                )
            )
        else:
            console.print("[red]Error: --by option is required.[/red]")
        raise typer.Exit(code=1)

    try:
        old_file, new_file = adr_supersede(
            old_adr=old_adr,
            by_new_adr=by_new_adr,
            dry_run=dry_run,
        )
    except (VaultSpecError, OSError) as exc:
        _handle_error(exc, json_output=json_output)
        return

    if json_output:
        status = "updated" if not dry_run else "unchanged"
        typer.echo(
            json.dumps(
                json_envelope(
                    "vault.adr.supersede",
                    status,
                    {
                        "old_path": str(old_file),
                        "new_path": str(new_file),
                    },
                ),
                **json_format_kwargs(),
            )
        )
        raise typer.Exit(0)

    action = "Would supersede ADR" if dry_run else "ADR superseded successfully"
    console.print(f"[green]{action}:[/green] {old_file} by {new_file}")

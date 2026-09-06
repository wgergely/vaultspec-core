"""Vault health check suite for ``.vault/`` content.

Re-exports the result contract
(:class:`~vaultspec_core.vaultcore.checks._base.CheckResult`,
:class:`~vaultspec_core.vaultcore.checks._base.CheckDiagnostic`,
:class:`~vaultspec_core.vaultcore.checks._base.Severity`) and all
checker functions from their submodules. Use :func:`run_all_checks` for a
combined pass or call individual checkers. Consumed by
:mod:`vaultspec_core.cli` and :mod:`vaultspec_core.mcp_server`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ._base import (
    CheckDiagnostic,
    CheckResult,
    Severity,
    VaultDocData,
    VaultSnapshot,
    render_check_result,
)
from .adr_status import check_adr_status
from .annotations import check_annotations
from .body_links import check_body_links
from .body_sections import check_body_sections
from .code_boundary import check_code_boundary
from .dangling import check_dangling
from .encoding import check_encoding
from .exec_mapping import check_exec_mapping
from .feature_rename_integrity import check_feature_rename_integrity
from .features import check_features
from .foreign import check_foreign
from .frontmatter import check_frontmatter
from .links import check_links
from .markdown import check_markdown
from .modified_stamp import check_modified_stamp
from .orphans import check_orphans
from .placeholders import check_placeholders
from .references import check_references, check_schema
from .rename_integrity import check_rename_integrity
from .structure import check_structure

if TYPE_CHECKING:
    from pathlib import Path

__all__ = [
    "CheckDiagnostic",
    "CheckResult",
    "Severity",
    "VaultDocData",
    "VaultSnapshot",
    "check_adr_status",
    "check_annotations",
    "check_body_links",
    "check_body_sections",
    "check_code_boundary",
    "check_dangling",
    "check_encoding",
    "check_exec_mapping",
    "check_feature_rename_integrity",
    "check_features",
    "check_foreign",
    "check_frontmatter",
    "check_links",
    "check_markdown",
    "check_modified_stamp",
    "check_orphans",
    "check_placeholders",
    "check_references",
    "check_rename_integrity",
    "check_schema",
    "check_structure",
    "render_check_result",
    "run_all_checks",
]


def run_all_checks(
    root_dir: Path,
    *,
    feature: str | None = None,
    fix: bool = False,
) -> list[CheckResult]:
    """Run all vault health checkers and return their results.

    Executes structure, frontmatter, annotations, markdown, links, dangling,
    body-links, placeholders, orphans, features, exec-mapping, body-sections,
    feature-rename-integrity, references, schema, adr-status, modified-stamp,
    rename-integrity, encoding, and foreign checks in order. Builds a single
    :class:`~vaultspec_core.graph.VaultGraph` and shares it across
    graph-consuming checkers to avoid redundant I/O.

    Args:
        root_dir: Project root directory.
        feature: Restrict per-document checks to this feature tag (without ``#``).
        fix: When ``True``, pass ``fix=True`` to all supporting checkers.

    Returns:
        List of :class:`~vaultspec_core.vaultcore.checks._base.CheckResult`,
        one per checker, in the order above.
    """
    from ...graph import VaultGraph

    if not fix:
        # The single-ingress contract: the graph build (or, after a cache
        # hit, ensure_raw_texts) reads each document exactly once, and the
        # whole calculate phase below runs from the shared snapshot and
        # raw-text map without another corpus read. check_rename_integrity
        # is exempt by scope: it validates .vaultspec/ workspace resources,
        # not the vault corpus.
        graph = VaultGraph(root_dir)
        graph.ensure_raw_texts()
        snapshot = graph.to_snapshot()
        raw_texts = graph.raw_texts
        return [
            check_structure(root_dir, snapshot=snapshot, fix=False),
            check_frontmatter(root_dir, snapshot=snapshot, feature=feature, fix=False),
            check_annotations(
                root_dir, feature=feature, fix=False, raw_texts=raw_texts
            ),
            check_markdown(root_dir, feature=feature, fix=False, raw_texts=raw_texts),
            check_links(root_dir, snapshot=snapshot, feature=feature, fix=False),
            check_dangling(root_dir, graph=graph, feature=feature, fix=False),
            check_body_links(root_dir, snapshot=snapshot, feature=feature, fix=False),
            check_placeholders(root_dir, snapshot=snapshot, feature=feature),
            check_orphans(root_dir, graph=graph, feature=feature),
            check_features(root_dir, snapshot=snapshot, feature=feature),
            check_exec_mapping(
                root_dir, snapshot=snapshot, feature=feature, raw_texts=raw_texts
            ),
            check_body_sections(root_dir, snapshot=snapshot, feature=feature),
            check_feature_rename_integrity(root_dir, snapshot=snapshot),
            check_references(root_dir, graph=graph, feature=feature, fix=False),
            check_schema(root_dir, graph=graph, feature=feature, fix=False),
            check_adr_status(root_dir, snapshot=snapshot, feature=feature, fix=False),
            # Last of the document-scoped checkers so its position matches the
            # --fix branch, where the staleness fingerprint must be compared
            # against bodies no later checker will still rewrite.
            check_modified_stamp(
                root_dir, snapshot=snapshot, feature=feature, fix=False
            ),
            check_rename_integrity(root_dir, fix=False),
            check_encoding(root_dir, graph=graph),
            check_foreign(root_dir),
        ]

    # Mutating checks can rename files or rewrite frontmatter. Refresh graph
    # state only after a checker reports a mutation.
    results: list[CheckResult] = []
    graph = VaultGraph(root_dir)

    def append_and_refresh(result: CheckResult) -> None:
        nonlocal graph
        results.append(result)
        if result.fixed_count:
            graph = VaultGraph(root_dir)

    result = check_structure(root_dir, snapshot=graph.to_snapshot(), fix=True)
    append_and_refresh(result)

    result = check_frontmatter(
        root_dir,
        snapshot=graph.to_snapshot(),
        feature=feature,
        fix=True,
    )
    append_and_refresh(result)

    result = check_annotations(root_dir, feature=feature, fix=True)
    append_and_refresh(result)

    # Markdown hygiene rewrites only line whitespace and blank runs - it never
    # touches frontmatter, links, or filenames, so it cannot invalidate the
    # graph's structure. Run it after annotations so blank lines left by
    # stripped comment blocks are collapsed in the same pass. It does rewrite
    # bodies, though, so refresh on a mutation: the modified-stamp fingerprint
    # below reads bodies from the snapshot and must see the hygiene result,
    # not the text that preceded it.
    append_and_refresh(check_markdown(root_dir, feature=feature, fix=True))

    result = check_links(
        root_dir, snapshot=graph.to_snapshot(), feature=feature, fix=True
    )
    append_and_refresh(result)

    result = check_dangling(root_dir, graph=graph, feature=feature, fix=True)
    append_and_refresh(result)

    append_and_refresh(
        check_body_links(
            root_dir, snapshot=graph.to_snapshot(), feature=feature, fix=True
        )
    )
    results.append(
        check_placeholders(root_dir, snapshot=graph.to_snapshot(), feature=feature)
    )
    results.append(check_orphans(root_dir, graph=graph, feature=feature))
    results.append(
        check_features(root_dir, snapshot=graph.to_snapshot(), feature=feature)
    )
    # Exec-mapping and body-sections are read-only (no dangling reference or
    # missing section has an unambiguous auto-repair); they run identically in
    # both modes, following the check_encoding precedent.
    results.append(
        check_exec_mapping(root_dir, snapshot=graph.to_snapshot(), feature=feature)
    )
    results.append(
        check_body_sections(root_dir, snapshot=graph.to_snapshot(), feature=feature)
    )
    # Feature-rename-integrity is read-only (reconciling drift is a feature
    # rename, not a frontmatter rewrite); it runs identically in both modes.
    results.append(check_feature_rename_integrity(root_dir))

    result = check_references(root_dir, graph=graph, feature=feature, fix=True)
    append_and_refresh(result)

    results.append(check_schema(root_dir, graph=graph, feature=feature, fix=True))

    # adr-status fix only rewrites the H1 status token's backtick quoting; it
    # never touches frontmatter, links, or filenames, so it cannot invalidate
    # the graph. Refresh anyway when it mutates, to keep the snapshot honest.
    result = check_adr_status(
        root_dir, snapshot=graph.to_snapshot(), feature=feature, fix=True
    )
    append_and_refresh(result)

    # Last of the document-scoped fixers, and deliberately so: staleness is a
    # comparison against the body as it finally stands, so every checker that
    # rewrites bodies - annotations, markdown hygiene, wiki-link repair, the
    # adr-status heading rewrite - must already have run. Its own fix writes
    # the stamp and re-attests the fingerprint together, so it converges
    # in-place and cannot invalidate anything downstream; appending without a
    # graph rebuild keeps the structure-rename cascade (which the repair
    # pipeline depends on) intact.
    result = check_modified_stamp(
        root_dir,
        snapshot=graph.to_snapshot(),
        feature=feature,
        fix=True,
    )
    results.append(result)

    results.append(check_rename_integrity(root_dir, fix=True))
    # Encoding is read-only (non-UTF-8 cannot be auto-rewritten without silently
    # mutating bytes); it runs identically in both modes.
    results.append(check_encoding(root_dir))
    # Foreign is read-only (a file the checker cannot identify is exactly the
    # file it must not act on); it runs identically in both modes.
    results.append(check_foreign(root_dir))
    return results

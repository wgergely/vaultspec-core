"""Check for orphaned vault documents with no incoming wiki-links."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ._base import CheckDiagnostic, CheckResult, Severity

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["check_orphans"]


def check_orphans(
    root_dir: Path,
    *,
    feature: str | None = None,
) -> CheckResult:
    """Find documents with no incoming wiki-links.

    Delegates orphan detection to
    :meth:`~vaultspec_core.graph.VaultGraph.get_orphaned`. Unreachable
    documents are flagged as WARNING-severity diagnostics; each diagnostic
    includes outgoing link targets as a suggested starting point.

    Args:
        root_dir: Project root directory.
        feature: Restrict results to documents with this feature tag
            (without ``#``).

    Returns:
        :class:`~vaultspec_core.vaultcore.checks._base.CheckResult` with
        check name ``"orphans"``. Does not support ``--fix``.
    """
    from ...graph import VaultGraph

    result = CheckResult(check_name="orphans", supports_fix=False)

    graph = VaultGraph(root_dir)
    orphan_names = graph.get_orphaned()

    for name in sorted(orphan_names):
        node = graph.nodes[name]

        if feature:
            feat = feature.lstrip("#")
            node_features = {t.lstrip("#") for t in node.tags}
            if feat not in node_features:
                continue

        doc_type_str = node.doc_type.value if node.doc_type else "unknown"
        rel_path = node.path.relative_to(root_dir)

        suggestion = ""
        if node.out_links:
            suggestion = f"Links out to: {', '.join(sorted(node.out_links)[:3])}"

        result.diagnostics.append(
            CheckDiagnostic(
                path=rel_path,
                message=f"Orphaned {doc_type_str} document — no incoming links",
                severity=Severity.WARNING,
                fix_description=suggestion or None,
            )
        )

    return result

"""Check for truly isolated vault documents with no graph connections."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ._base import CheckDiagnostic, CheckResult, Severity

if TYPE_CHECKING:
    from pathlib import Path

    from ...graph import VaultGraph


__all__ = ["check_orphans"]


def check_orphans(
    root_dir: Path,
    *,
    graph: VaultGraph,
    feature: str | None = None,
) -> CheckResult:
    """Find documents that are completely isolated from the vault graph.

    A document is orphaned only when it has no incoming links, no outgoing
    links, and no sibling documents sharing the same feature tag.  Exec
    records and summaries that link out to their parent plan are connected
    and therefore not orphans.

    Delegates detection to
    :meth:`~vaultspec_core.graph.VaultGraph.get_orphaned`.

    Args:
        root_dir: Project root directory.
        graph: Pre-built vault graph to query (avoids redundant I/O).
        feature: Restrict results to documents with this feature tag
            (without ``#``).

    Returns:
        :class:`~vaultspec_core.vaultcore.checks._base.CheckResult` with
        check name ``"orphans"``. Does not support ``--fix``.
    """
    result = CheckResult(check_name="orphans", supports_fix=False)
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

        result.diagnostics.append(
            CheckDiagnostic(
                path=rel_path,
                message=(
                    f"Isolated {doc_type_str} document - no links or feature siblings"
                ),
                severity=Severity.WARNING,
            )
        )

    return result

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

    These documents are unreachable from any other vault document.
    """
    from ...graph import VaultGraph

    result = CheckResult(check_name="orphans", supports_fix=False)

    graph = VaultGraph(root_dir)
    orphan_names = graph.get_orphaned()

    for name in sorted(orphan_names):
        node = graph.nodes[name]

        # Feature filter (normalize: always compare stripped values)
        if feature:
            feat = feature.lstrip("#")
            node_features = {t.lstrip("#") for t in node.tags}
            if feat not in node_features:
                continue

        doc_type_str = node.doc_type.value if node.doc_type else "unknown"
        rel_path = node.path.relative_to(root_dir)

        # Suggest potential link targets based on name similarity
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

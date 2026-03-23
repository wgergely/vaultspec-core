"""Vault health check suite for ``.vault/`` content.

Re-exports the result contract
(:class:`~vaultspec_core.vaultcore.checks._base.CheckResult`,
:class:`~vaultspec_core.vaultcore.checks._base.CheckDiagnostic`,
:class:`~vaultspec_core.vaultcore.checks._base.Severity`) and all seven
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
from .dangling import check_dangling
from .features import check_features
from .frontmatter import check_frontmatter
from .links import check_links
from .orphans import check_orphans
from .references import check_references, check_schema
from .structure import check_structure

if TYPE_CHECKING:
    from pathlib import Path

__all__ = [
    "CheckDiagnostic",
    "CheckResult",
    "Severity",
    "VaultDocData",
    "VaultSnapshot",
    "check_dangling",
    "check_features",
    "check_frontmatter",
    "check_links",
    "check_orphans",
    "check_references",
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
    """Run all eight vault health checkers and return their results.

    Executes structure, frontmatter, links, dangling, orphans, features,
    references, and schema checks in order. Builds a single
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

    graph = VaultGraph(root_dir)
    snapshot = graph.to_snapshot()

    return [
        check_structure(root_dir, snapshot=snapshot, fix=fix),
        check_frontmatter(root_dir, snapshot=snapshot, feature=feature, fix=fix),
        check_links(root_dir, snapshot=snapshot, feature=feature, fix=fix),
        check_dangling(root_dir, graph=graph, feature=feature, fix=fix),
        check_orphans(root_dir, graph=graph, feature=feature),
        check_features(root_dir, snapshot=snapshot, feature=feature),
        check_references(root_dir, graph=graph, feature=feature, fix=fix),
        check_schema(root_dir, graph=graph, feature=feature, fix=fix),
    ]

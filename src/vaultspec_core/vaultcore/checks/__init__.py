"""Vault health check suite.

Each checker returns a CheckResult with per-document diagnostics.
Use run_all_checks() for a combined pass or call individual checkers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ._base import CheckDiagnostic, CheckResult, Severity, render_check_result
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
    """Run all vault health checks and return combined results."""
    return [
        check_structure(root_dir, fix=fix),
        check_frontmatter(root_dir, feature=feature, fix=fix),
        check_links(root_dir, feature=feature, fix=fix),
        check_orphans(root_dir, feature=feature),
        check_features(root_dir, feature=feature),
        check_references(root_dir, feature=feature, fix=fix),
        check_schema(root_dir, feature=feature, fix=fix),
    ]

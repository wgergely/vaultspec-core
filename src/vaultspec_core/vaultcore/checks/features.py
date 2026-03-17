"""Check feature tag completeness — detect features missing required doc types."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ._base import CheckDiagnostic, CheckResult, Severity

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["check_features"]


def check_features(
    root_dir: Path,
    *,
    feature: str | None = None,
) -> CheckResult:
    """Check that features have appropriate document type coverage.

    Rules:
    - Feature with only exec docs but no plan or ADR: WARNING
    - Feature with plan but no ADR: WARNING
    - Feature with ADR but no research: INFO (soft recommendation)
    """
    from ..query import _scan_all

    result = CheckResult(check_name="features", supports_fix=False)

    docs = _scan_all(root_dir)

    # Group by feature
    by_feature: dict[str, set[str]] = {}
    for d in docs:
        if d.feature:
            by_feature.setdefault(d.feature, set()).add(d.doc_type)

    # Filter
    if feature:
        feat = feature.lstrip("#")
        by_feature = {k: v for k, v in by_feature.items() if k == feat}

    for feat_name, types in sorted(by_feature.items()):
        if feat_name == "uncategorized":
            continue

        has_adr = "adr" in types
        has_plan = "plan" in types
        has_research = "research" in types
        has_exec = "exec" in types
        # Exec-only features lack planning docs
        if has_exec and not has_plan and not has_adr:
            result.diagnostics.append(
                CheckDiagnostic(
                    path=None,
                    message=(
                        f"Feature '{feat_name}' has execution records but "
                        f"no plan or ADR. Types present: {', '.join(sorted(types))}"
                    ),
                    severity=Severity.WARNING,
                    fix_description=(
                        f"Consider: vault add plan -f {feat_name} && "
                        f"vault add adr -f {feat_name}"
                    ),
                )
            )

        # Plan without ADR
        if has_plan and not has_adr:
            result.diagnostics.append(
                CheckDiagnostic(
                    path=None,
                    message=(
                        f"Feature '{feat_name}' has a plan but no ADR. "
                        f"Plans should be backed by an architectural decision."
                    ),
                    severity=Severity.WARNING,
                    fix_description=f"Consider: vault add adr -f {feat_name}",
                )
            )

        # ADR without research (soft check)
        if has_adr and not has_research:
            result.diagnostics.append(
                CheckDiagnostic(
                    path=None,
                    message=(
                        f"Feature '{feat_name}' has an ADR but no research document. "
                        f"Research docs help justify architectural decisions."
                    ),
                    severity=Severity.INFO,
                    fix_description=f"Consider: vault add research -f {feat_name}",
                )
            )

    return result

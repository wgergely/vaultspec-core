"""Check feature tag completeness  - detect features missing required doc types."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ._base import (
    CheckDiagnostic,
    CheckResult,
    Severity,
    VaultSnapshot,
    extract_feature_tags,
    is_generated_index,
)

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["check_features"]


def _count_index_related(snapshot: VaultSnapshot) -> dict[str, int]:
    """Return a mapping of feature name to ``related:`` count for indexes.

    Only considers files matching the ``*.index.md`` naming convention.
    """
    counts: dict[str, int] = {}
    for doc_path, (metadata, _body) in snapshot.items():
        if not is_generated_index(doc_path):
            continue
        # Feature name is the stem minus ".index" suffix
        stem = doc_path.stem  # e.g. "my-feature.index"
        feat = stem.removesuffix(".index")
        counts[feat] = len(metadata.related)
    return counts


def _index_exists_for(
    feat_name: str,
    snapshot: VaultSnapshot,
) -> bool:
    """Return ``True`` if a ``<feat_name>.index.md`` exists in the snapshot."""
    return any(doc_path.name == f"{feat_name}.index.md" for doc_path in snapshot)


def _count_feature_docs(
    feat_name: str,
    snapshot: VaultSnapshot,
) -> int:
    """Count non-index documents tagged with *feat_name*."""
    count = 0
    for doc_path, (metadata, _body) in snapshot.items():
        if is_generated_index(doc_path):
            continue
        if feat_name in extract_feature_tags(metadata.tags):
            count += 1
    return count


def check_features(
    root_dir: Path,
    *,
    snapshot: VaultSnapshot,
    feature: str | None = None,
) -> CheckResult:
    """Check that features have appropriate document type coverage.

    Rules enforced:

    - exec only, no plan or ADR: WARNING
    - plan present, no ADR: WARNING
    - ADR present, no research: INFO (soft recommendation)
    - feature has documents but no ``<feature>.index.md``: WARNING
    - feature index exists but ``related:`` count differs from actual
      document count: WARNING (stale index)

    Args:
        root_dir: Project root directory.
        snapshot: Pre-built snapshot mapping document paths to parsed data.
        feature: Restrict checks to a single feature (without ``#``).

    Returns:
        :class:`~vaultspec_core.vaultcore.checks._base.CheckResult` with
        check name ``"features"``. Does not support ``--fix``.
    """
    from ..scanner import get_doc_type

    result = CheckResult(check_name="features", supports_fix=False)

    by_feature: dict[str, set[str]] = {}
    for doc_path, (metadata, _body) in snapshot.items():
        if is_generated_index(doc_path):
            continue
        feat_tags = extract_feature_tags(metadata.tags)
        dt = get_doc_type(doc_path, root_dir)
        dt_value = dt.value if dt else None
        for ft in feat_tags:
            if dt_value:
                by_feature.setdefault(ft, set()).add(dt_value)

    if feature:
        feat = feature.lstrip("#")
        by_feature = {k: v for k, v in by_feature.items() if k == feat}

    index_related_counts = _count_index_related(snapshot)

    for feat_name, types in sorted(by_feature.items()):
        if feat_name == "uncategorized":
            continue

        has_adr = "adr" in types
        has_plan = "plan" in types
        has_research = "research" in types
        has_exec = "exec" in types
        if has_exec and not has_plan and not has_adr:
            result.diagnostics.append(
                CheckDiagnostic(
                    path=None,
                    message=(
                        f"Feature '{feat_name}' has execution records "
                        f"but no plan or ADR. "
                        f"Types present: {', '.join(sorted(types))}"
                    ),
                    severity=Severity.WARNING,
                    fix_description=(
                        f"Consider: vault add plan -f {feat_name} && "
                        f"vault add adr -f {feat_name}"
                    ),
                )
            )

        if has_plan and not has_adr:
            result.diagnostics.append(
                CheckDiagnostic(
                    path=None,
                    message=(
                        f"Feature '{feat_name}' has a plan but no ADR. "
                        f"Plans should be backed by an "
                        f"architectural decision."
                    ),
                    severity=Severity.WARNING,
                    fix_description=(f"Consider: vault add adr -f {feat_name}"),
                )
            )

        if has_adr and not has_research:
            result.diagnostics.append(
                CheckDiagnostic(
                    path=None,
                    message=(
                        f"Feature '{feat_name}' has an ADR but no "
                        f"research document. Research docs help "
                        f"justify architectural decisions."
                    ),
                    severity=Severity.INFO,
                    fix_description=(f"Consider: vault add research -f {feat_name}"),
                )
            )

        # -- Index health checks --

        if not _index_exists_for(feat_name, snapshot):
            result.diagnostics.append(
                CheckDiagnostic(
                    path=None,
                    message=(
                        f"Feature '{feat_name}' has no feature index. "
                        f"Run vault feature index to generate "
                        f"{feat_name}.index.md"
                    ),
                    severity=Severity.WARNING,
                    fix_description=(f"vault feature index -f {feat_name}"),
                )
            )
        else:
            # Index exists - check staleness
            actual_count = _count_feature_docs(feat_name, snapshot)
            index_count = index_related_counts.get(feat_name, 0)
            if index_count != actual_count:
                result.diagnostics.append(
                    CheckDiagnostic(
                        path=None,
                        message=(
                            f"Feature '{feat_name}' index is stale: "
                            f"related: has {index_count} links but "
                            f"feature has {actual_count} documents. "
                            f"Run vault feature index to rebuild"
                        ),
                        severity=Severity.WARNING,
                        fix_description=(f"vault feature index -f {feat_name}"),
                    )
                )

    return result

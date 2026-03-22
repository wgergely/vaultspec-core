"""Check missing cross-references and enforce schema rules.

Two checks in one module:
- references: feature docs that should reference each other but don't
- schema: ADRs must reference research, plans must reference ADRs

Both support ``--fix`` to auto-add ``related:`` links in frontmatter.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from ._base import CheckDiagnostic, CheckResult, Severity

if TYPE_CHECKING:
    from pathlib import Path

    from ...graph import VaultGraph

__all__ = ["check_references", "check_schema"]

logger = logging.getLogger(__name__)


def _add_related_link(doc_path: Path, link_name: str) -> bool:
    """Append a ``[[wiki-link]]`` to the ``related:`` field in frontmatter.

    Creates the ``related:`` field if absent. No-ops when the link is
    already present anywhere in the file.

    Args:
        doc_path: Absolute path to the vault document to modify.
        link_name: Stem of the target document (without ``[[]]`` wrappers).

    Returns:
        ``True`` if the file was modified, ``False`` otherwise.
    """
    try:
        content = doc_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False

    link = f"[[{link_name}]]"

    # Already present in related or body
    if link in content:
        return False

    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", content.lstrip(), re.DOTALL)
    if not match:
        return False

    yaml_block = match.group(1)
    body = match.group(2)
    leading_ws = content[: len(content) - len(content.lstrip())]

    # Check if related: field exists
    if re.search(r"^related:", yaml_block, re.MULTILINE):
        # Find the last list item under related: and append after it
        last_item = re.search(r"(^related:.*(?:\n  - .+)*)", yaml_block, re.MULTILINE)
        if last_item:
            new_yaml = (
                yaml_block[: last_item.end()]
                + f'\n  - "{link}"'
                + yaml_block[last_item.end() :]
            )
        else:
            new_yaml = re.sub(
                r"(^related:.*$)",
                rf'\1\n  - "{link}"',
                yaml_block,
                count=1,
                flags=re.MULTILINE,
            )
    else:
        # Add related: field before closing ---
        new_yaml = yaml_block + f'\nrelated:\n  - "{link}"'

    new_content = f"{leading_ws}---\n{new_yaml}\n---\n{body}"
    doc_path.write_text(new_content, encoding="utf-8")
    logger.info("Added %s to related field in %s", link, doc_path.name)
    return True


def check_references(
    root_dir: Path,
    *,
    graph: VaultGraph,
    feature: str | None = None,
    fix: bool = False,
) -> CheckResult:
    """Check for missing cross-references within features.

    For each feature, finds research documents not referenced by any plan
    or ADR in the same feature.

    Args:
        root_dir: Project root directory.
        graph: Pre-built vault graph to query (avoids redundant I/O).
        feature: Restrict checks to a single feature (without ``#``).
        fix: When ``True``, adds the missing ``[[wiki-link]]`` to the
            ``related:`` field of the first available ADR or plan.

    Returns:
        :class:`~vaultspec_core.vaultcore.checks._base.CheckResult` with
        check name ``"references"``.
    """
    from ..models import DocType

    result = CheckResult(check_name="references", supports_fix=True)

    # Group nodes by feature
    by_feature: dict[str, dict[str, list]] = {}
    for _name, node in graph.nodes.items():
        for tag in node.tags:
            if not DocType.from_tag(tag):
                feat = tag.lstrip("#")
                by_feature.setdefault(feat, {}).setdefault(
                    node.doc_type.value if node.doc_type else "unknown", []
                ).append(node)

    if feature:
        feat = feature.lstrip("#")
        by_feature = {k: v for k, v in by_feature.items() if k == feat}

    for feat_name, types_map in sorted(by_feature.items()):
        if feat_name == "uncategorized":
            continue

        research_docs = types_map.get("research", [])
        plan_docs = types_map.get("plan", [])
        adr_docs = types_map.get("adr", [])

        if not research_docs:
            continue

        # Collect all outgoing links from plans and ADRs in this feature
        plan_adr_links: set[str] = set()
        for doc in plan_docs + adr_docs:
            plan_adr_links.update(doc.out_links)

        # Check if research docs are referenced
        for research_node in research_docs:
            if research_node.name not in plan_adr_links:
                referencing_types = []
                if plan_docs:
                    referencing_types.append("plan")
                if adr_docs:
                    referencing_types.append("ADR")

                if not referencing_types:
                    continue

                if fix:
                    # Add to the first ADR or plan in this feature
                    target_doc = (adr_docs or plan_docs)[0]
                    if _add_related_link(target_doc.path, research_node.name):
                        result.fixed_count += 1
                        result.diagnostics.append(
                            CheckDiagnostic(
                                path=target_doc.path.relative_to(root_dir),
                                message=(
                                    f"Fixed: added [[{research_node.name}]] "
                                    f"to related field"
                                ),
                                severity=Severity.INFO,
                            )
                        )
                        continue

                result.diagnostics.append(
                    CheckDiagnostic(
                        path=research_node.path.relative_to(root_dir),
                        message=(
                            f"Research doc not referenced by any "
                            f"{'/'.join(referencing_types)} in feature "
                            f"'{feat_name}'"
                        ),
                        severity=Severity.WARNING,
                        fixable=True,
                        fix_description=(
                            f"Add [[{research_node.name}]] to related field "
                            f"in a {'/'.join(referencing_types)} document"
                        ),
                    )
                )

    return result


def check_schema(
    root_dir: Path,
    *,
    graph: VaultGraph,
    feature: str | None = None,
    doc_type_filter: str | None = None,
    fix: bool = False,
) -> CheckResult:
    """Enforce schema-level cross-reference rules on ADRs and plans.

    Rules enforced:

    - ADR must reference at least one research document (ERROR).
    - Plan must reference at least one ADR (ERROR).
    - Plan should reference research documents (WARNING).

    With ``fix=True``, adds the first matching document of the required type
    found within the same feature to the ``related:`` field.

    Args:
        root_dir: Project root directory.
        graph: Pre-built vault graph to query (avoids redundant I/O).
        feature: Restrict checks to documents with this feature tag
            (without ``#``).
        doc_type_filter: Restrict checks to this document type
            (e.g. ``"adr"``).
        fix: When ``True``, attempt to auto-add the missing ``[[wiki-link]]``.

    Returns:
        :class:`~vaultspec_core.vaultcore.checks._base.CheckResult` with
        check name ``"schema"``.
    """
    from ..models import DocType

    result = CheckResult(check_name="schema", supports_fix=True)

    # Pre-build feature→type→nodes index for fix lookups
    feat_type_index: dict[str, dict[str, list]] = {}
    for _name, _node in graph.nodes.items():
        if not _node.doc_type:
            continue
        for _tag in _node.tags:
            if not DocType.from_tag(_tag):
                _feat = _tag.lstrip("#")
                feat_type_index.setdefault(_feat, {}).setdefault(
                    _node.doc_type.value, []
                ).append(_node)

    for _name, node in sorted(graph.nodes.items()):
        if not node.doc_type:
            continue

        # Apply filters
        if doc_type_filter and node.doc_type.value != doc_type_filter:
            continue
        # Feature filter (normalize: always compare stripped values)
        if feature:
            feat = feature.lstrip("#")
            node_features = {t.lstrip("#") for t in node.tags}
            if feat not in node_features:
                continue

        # Classify outgoing link targets by doc type
        linked_types: set[str] = set()
        for target_name in node.out_links:
            target = graph.nodes.get(target_name)
            if target and target.doc_type:
                linked_types.add(target.doc_type.value)

        rel_path = node.path.relative_to(root_dir)
        feat_tags = [t for t in node.tags if not DocType.from_tag(t)]
        feat_name = feat_tags[0].lstrip("#") if feat_tags else None

        if node.doc_type == DocType.ADR:
            if "research" not in linked_types:
                msg = "ADR has no references to research documents"
                if feat_name:
                    msg += f" (feature: {feat_name})"

                if fix and feat_name:
                    candidates = feat_type_index.get(feat_name, {}).get("research", [])
                    if candidates and _add_related_link(node.path, candidates[0].name):
                        result.fixed_count += 1
                        result.diagnostics.append(
                            CheckDiagnostic(
                                path=rel_path,
                                message=(
                                    f"Fixed: added [[{candidates[0].name}]] "
                                    f"to related field"
                                ),
                                severity=Severity.INFO,
                            )
                        )
                        continue

                result.diagnostics.append(
                    CheckDiagnostic(
                        path=rel_path,
                        message=msg,
                        severity=Severity.ERROR,
                        fixable=True,
                        fix_description=(
                            "Add a research document reference in the "
                            "related field or document body"
                        ),
                    )
                )

        elif node.doc_type == DocType.PLAN:
            if "adr" not in linked_types:
                if fix and feat_name:
                    candidates = feat_type_index.get(feat_name, {}).get("adr", [])
                    if candidates and _add_related_link(node.path, candidates[0].name):
                        result.fixed_count += 1
                        result.diagnostics.append(
                            CheckDiagnostic(
                                path=rel_path,
                                message=(
                                    f"Fixed: added [[{candidates[0].name}]] "
                                    f"to related field"
                                ),
                                severity=Severity.INFO,
                            )
                        )
                    else:
                        result.diagnostics.append(
                            CheckDiagnostic(
                                path=rel_path,
                                message="Plan has no references to ADR documents",
                                severity=Severity.ERROR,
                                fixable=True,
                                fix_description=(
                                    "Add an ADR document reference in the "
                                    "related field or document body"
                                ),
                            )
                        )
                else:
                    result.diagnostics.append(
                        CheckDiagnostic(
                            path=rel_path,
                            message="Plan has no references to ADR documents",
                            severity=Severity.ERROR,
                            fixable=True,
                            fix_description=(
                                "Add an ADR document reference in the "
                                "related field or document body"
                            ),
                        )
                    )

            # Plans should reference research (soft)
            if "research" not in linked_types:
                if fix and feat_name:
                    candidates = feat_type_index.get(feat_name, {}).get("research", [])
                    if candidates and _add_related_link(node.path, candidates[0].name):
                        result.fixed_count += 1
                        result.diagnostics.append(
                            CheckDiagnostic(
                                path=rel_path,
                                message=(
                                    f"Fixed: added [[{candidates[0].name}]] "
                                    f"to related field"
                                ),
                                severity=Severity.INFO,
                            )
                        )
                    else:
                        result.diagnostics.append(
                            CheckDiagnostic(
                                path=rel_path,
                                message="Plan has no references to research documents",
                                severity=Severity.WARNING,
                                fix_description=(
                                    "Consider adding research document references "
                                    "for supporting evidence"
                                ),
                            )
                        )
                else:
                    result.diagnostics.append(
                        CheckDiagnostic(
                            path=rel_path,
                            message="Plan has no references to research documents",
                            severity=Severity.WARNING,
                            fix_description=(
                                "Consider adding research document references "
                                "for supporting evidence"
                            ),
                        )
                    )

    return result

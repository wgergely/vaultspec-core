"""Check missing cross-references and enforce schema rules.

Two checks in one module:
- references: feature docs that should reference each other but don't
- schema: ADRs must reference grounding (research/reference/audit);
  plans must reference ADRs

Both support ``--fix`` to auto-add ``related:`` links in frontmatter.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from ...core.helpers import atomic_write
from ._base import CheckDiagnostic, CheckResult, Severity

if TYPE_CHECKING:
    from pathlib import Path

    from ...graph import DocNode, VaultGraph

__all__ = ["check_references", "check_schema"]

logger = logging.getLogger(__name__)


def _add_related_link(doc_path: Path, root_dir: Path, link_name: str) -> bool:
    """Append a ``[[wiki-link]]`` to the ``related:`` field in frontmatter.

    Creates the ``related:`` field if absent. No-ops when the link is
    already present anywhere in the file.

    The read, the frontmatter surgery, and the write are one critical
    section on *doc_path*'s per-document advisory lock - the same sentinel
    ``execute_edit`` takes. The already-present short-circuit is re-derived
    inside it too, so a link another writer added between the checker's
    graph build and this call is seen rather than duplicated.

    Args:
        doc_path: Absolute path to the vault document to modify.
        root_dir: Project root owning the document's ``.vault/``.
        link_name: Stem of the target document (without ``[[]]`` wrappers).

    Returns:
        ``True`` if the file was modified, ``False`` otherwise.
    """
    from ..edit_engine import document_write_lock

    with document_write_lock(doc_path, root_dir):
        return _add_related_link_locked(doc_path, link_name)


def _add_related_link_locked(doc_path: Path, link_name: str) -> bool:
    """Perform the ``related:`` append under *doc_path*'s already-held lock.

    Args:
        doc_path: Absolute path to the vault document to modify.
        link_name: Stem of the target document (without ``[[]]`` wrappers).

    Returns:
        ``True`` if the file was modified, ``False`` otherwise.
    """
    try:
        # Read as bytes and decode without universal newlines so the
        # source CRLF/LF convention is observable; we restore it on the
        # written output below.
        raw_content = doc_path.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return False

    source_newline = "\r\n" if "\r\n" in raw_content else "\n"
    content = raw_content.replace("\r\n", "\n")

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

    empty_related = re.compile(r"^related:\s*\[\s*\]\s*$", re.MULTILINE)
    if empty_related.search(yaml_block):
        new_yaml = empty_related.sub(f"related:\n  - '{link}'", yaml_block, count=1)
    elif re.search(r"^related:", yaml_block, re.MULTILINE):
        # Find the last list item under related: and append after it
        last_item = re.search(r"(^related:.*(?:\n  - .+)*)", yaml_block, re.MULTILINE)
        if last_item:
            new_yaml = (
                yaml_block[: last_item.end()]
                + f"\n  - '{link}'"
                + yaml_block[last_item.end() :]
            )
        else:
            new_yaml = re.sub(
                r"(^related:.*$)",
                rf"\1\n  - '{link}'",
                yaml_block,
                count=1,
                flags=re.MULTILINE,
            )
    else:
        # Add related: field before closing ---
        new_yaml = yaml_block + f"\nrelated:\n  - '{link}'"

    rendered = f"{leading_ws}---\n{new_yaml}\n---\n{body}"
    new_content = (
        rendered if source_newline == "\n" else rendered.replace("\n", source_newline)
    )
    atomic_write(doc_path, new_content)
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

    # Group nodes by feature (skip phantoms - they have no real doc type)
    by_feature: dict[str, dict[str, list[DocNode]]] = {}
    for _name, node in graph.nodes.items():
        if node.phantom:
            continue
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
                referencing_types: list[str] = []
                if plan_docs:
                    referencing_types.append("plan")
                if adr_docs:
                    referencing_types.append("ADR")

                if not referencing_types:
                    continue

                if fix:
                    # Add to the first ADR or plan in this feature
                    target_doc = (adr_docs or plan_docs)[0]
                    if target_doc.path is not None and _add_related_link(
                        target_doc.path, root_dir, research_node.name
                    ):
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
                        path=(
                            research_node.path.relative_to(root_dir)
                            if research_node.path is not None
                            else None
                        ),
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


def _build_feature_type_index(graph: VaultGraph) -> dict[str, dict[str, list[DocNode]]]:
    """Index real nodes by feature tag and document type for fix lookups."""
    from ..models import DocType

    feat_type_index: dict[str, dict[str, list[DocNode]]] = {}
    for node in graph.nodes.values():
        if node.phantom or not node.doc_type:
            continue
        for tag in node.tags:
            if not DocType.from_tag(tag):
                feat = tag.lstrip("#")
                feat_type_index.setdefault(feat, {}).setdefault(
                    node.doc_type.value, []
                ).append(node)
    return feat_type_index


def _is_filtered_out(
    node: DocNode, feature: str | None, doc_type_filter: str | None
) -> bool:
    """Return True when *node* falls outside the requested type/feature filter.

    An untyped node cannot satisfy a type filter, so it is filtered out. The
    caller already skips those, but stating it here keeps the helper correct
    on its own terms rather than relying on narrowing it cannot see.
    """
    if doc_type_filter and (
        node.doc_type is None or node.doc_type.value != doc_type_filter
    ):
        return True
    if not feature:
        return False
    # Feature filter (normalize: always compare stripped values)
    feat = feature.lstrip("#")
    return feat not in {t.lstrip("#") for t in node.tags}


def _linked_doc_types(graph: VaultGraph, node: DocNode) -> set[str]:
    """Classify outgoing link targets by doc type (skip phantoms)."""
    linked_types: set[str] = set()
    for target_name in node.out_links:
        target = graph.nodes.get(target_name)
        if target and not target.phantom and target.doc_type:
            linked_types.add(target.doc_type.value)
    return linked_types


def _primary_feature_name(node: DocNode) -> str | None:
    """Return the node's first feature tag without its ``#``, if any."""
    from ..models import DocType

    feat_tags = [t for t in node.tags if not DocType.from_tag(t)]
    return feat_tags[0].lstrip("#") if feat_tags else None


def _fix_missing_link(
    node: DocNode,
    root_dir: Path,
    rel_path: Path,
    feat_name: str | None,
    feat_type_index: dict[str, dict[str, list[DocNode]]],
    candidate_types: tuple[str, ...],
    result: CheckResult,
    *,
    fix: bool,
) -> bool:
    """Add the first same-feature document of *candidate_types* to ``related:``.

    Returns ``True`` when a link was added and the INFO diagnostic recorded,
    ``False`` when fixing is disabled or no candidate could be linked.

    A node with no working-tree path (a phantom, or a ref-scoped node whose
    blob lives only in git) has no file to rewrite, so it is never fixable.
    The caller already skips those; the guard is restated here so the helper
    holds on its own terms rather than on narrowing it cannot see.
    """
    if not fix or not feat_name or node.path is None:
        return False
    by_type = feat_type_index.get(feat_name, {})
    no_candidates: list[DocNode] = []
    candidates = next(
        (by_type[t] for t in candidate_types if by_type.get(t)), no_candidates
    )
    if not candidates or not _add_related_link(node.path, root_dir, candidates[0].name):
        return False
    result.fixed_count += 1
    result.diagnostics.append(
        CheckDiagnostic(
            path=rel_path,
            message=(f"Fixed: added [[{candidates[0].name}]] to related field"),
            severity=Severity.INFO,
        )
    )
    return True


def _check_adr_grounding(
    node: DocNode,
    root_dir: Path,
    rel_path: Path,
    feat_name: str | None,
    linked_types: set[str],
    feat_type_index: dict[str, dict[str, list[DocNode]]],
    result: CheckResult,
    *,
    fix: bool,
) -> None:
    """Require an ADR to reference research, reference, or audit grounding."""
    # The documentation hierarchy sanctions research, reference, and audit
    # documents as ADR grounding; any one of them satisfies the check.
    grounding_types = ("research", "reference", "audit")
    if linked_types & set(grounding_types):
        return

    if _fix_missing_link(
        node,
        root_dir,
        rel_path,
        feat_name,
        feat_type_index,
        grounding_types,
        result,
        fix=fix,
    ):
        return

    msg = "ADR has no grounding references (research, reference, or audit documents)"
    if feat_name:
        msg += f" (feature: {feat_name})"
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


def _check_plan_grounding(
    node: DocNode,
    root_dir: Path,
    rel_path: Path,
    feat_name: str | None,
    linked_types: set[str],
    feat_type_index: dict[str, dict[str, list[DocNode]]],
    result: CheckResult,
    *,
    fix: bool,
) -> None:
    """Require a plan to reference an ADR, and nudge it toward research."""
    if "adr" not in linked_types and not _fix_missing_link(
        node, root_dir, rel_path, feat_name, feat_type_index, ("adr",), result, fix=fix
    ):
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

    # Plans should rest on evidence (soft). The framework treats research,
    # reference, and audit documents as interchangeable grounding - the ADR
    # grounding check above accepts the same three - so a plan executing an
    # ADR off the back of an audit is grounded, not unevidenced.
    grounding_types = ("research", "reference", "audit")
    if not linked_types & set(grounding_types) and not _fix_missing_link(
        node,
        root_dir,
        rel_path,
        feat_name,
        feat_type_index,
        grounding_types,
        result,
        fix=fix,
    ):
        result.diagnostics.append(
            CheckDiagnostic(
                path=rel_path,
                message=(
                    "Plan has no grounding references (research, reference, "
                    "or audit documents)"
                ),
                severity=Severity.WARNING,
                fix_description=(
                    "Consider adding a research, reference, or audit "
                    "document reference for supporting evidence"
                ),
            )
        )


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

    - ADR must reference at least one grounding document - research,
      reference, or audit (ERROR).
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

    # Pre-build feature->type->nodes index for fix lookups (skip phantoms)
    feat_type_index = _build_feature_type_index(graph)

    for _name, node in sorted(graph.nodes.items()):
        if not node.doc_type or node.path is None:
            continue

        if _is_filtered_out(node, feature, doc_type_filter):
            continue

        linked_types = _linked_doc_types(graph, node)
        rel_path = node.path.relative_to(root_dir)
        feat_name = _primary_feature_name(node)

        if node.doc_type == DocType.ADR:
            _check_adr_grounding(
                node,
                root_dir,
                rel_path,
                feat_name,
                linked_types,
                feat_type_index,
                result,
                fix=fix,
            )
        elif node.doc_type == DocType.PLAN:
            _check_plan_grounding(
                node,
                root_dir,
                rel_path,
                feat_name,
                linked_types,
                feat_type_index,
                result,
                fix=fix,
            )

    return result

"""Unified query engine for .vault/ document operations.

Composes scanner, parser, graph, and metrics into a single query surface
used by CLI commands (vault stats, vault list, vault feature list).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .models import DocType

if TYPE_CHECKING:
    from pathlib import Path
from .parser import parse_frontmatter
from .scanner import get_doc_type, scan_vault


@dataclass
class VaultDocument:
    """A resolved vault document with parsed metadata."""

    path: Path
    name: str
    doc_type: str
    feature: str | None
    date: str | None
    tags: list[str]


def _parse_date_from_filename(name: str) -> str | None:
    """Extract YYYY-MM-DD prefix from filename."""
    m = re.match(r"(\d{4}-\d{2}-\d{2})", name)
    return m.group(1) if m else None


def _parse_feature_from_tags(tags: list[str], doc_type_tag: str | None) -> str | None:
    """Extract feature name from tags (the non-type tag)."""
    for tag in tags:
        cleaned = tag.lstrip("#")
        if doc_type_tag and cleaned == doc_type_tag:
            continue
        if cleaned in {dt.value for dt in DocType}:
            continue
        return cleaned
    return None


def _scan_all(root_dir: Path) -> list[VaultDocument]:
    """Scan vault and parse all documents into VaultDocument objects."""
    docs = []
    for doc_path in scan_vault(root_dir):
        try:
            content = doc_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        meta, _ = parse_frontmatter(content)
        dt = get_doc_type(doc_path, root_dir)
        dt_str = dt.value if dt else "unknown"
        tags = meta.get("tags", [])
        if isinstance(tags, str):
            tags = [tags]
        feature = _parse_feature_from_tags(tags, dt_str)
        date = meta.get("date") or _parse_date_from_filename(doc_path.name)

        docs.append(
            VaultDocument(
                path=doc_path,
                name=doc_path.stem,
                doc_type=dt_str,
                feature=feature,
                date=str(date) if date else None,
                tags=tags,
            )
        )
    return docs


def list_documents(
    root_dir: Path,
    *,
    doc_type: str | None = None,
    feature: str | None = None,
    date: str | None = None,
) -> list[VaultDocument]:
    """List vault documents with optional filters.

    Args:
        root_dir: Project root directory.
        doc_type: Filter by type. Standard types: adr, audit, exec, plan,
            reference, research. Special types: "orphaned", "invalid".
        feature: Filter by feature tag (without # prefix).
        date: Filter by date string (YYYY-MM-DD).
    """
    docs = _scan_all(root_dir)

    if doc_type == "orphaned":
        from ..graph import VaultGraph

        graph = VaultGraph(root_dir)
        orphan_names = set(graph.get_orphaned())
        docs = [d for d in docs if d.name in orphan_names]
    elif doc_type == "invalid":
        from ..graph import VaultGraph

        graph = VaultGraph(root_dir)
        invalid_sources = {src for src, _ in graph.get_invalid_links()}
        docs = [d for d in docs if d.name in invalid_sources]
    elif doc_type:
        docs = [d for d in docs if d.doc_type == doc_type]

    if feature:
        feature = feature.lstrip("#")
        docs = [d for d in docs if d.feature == feature]

    if date:
        docs = [d for d in docs if d.date == date]

    return docs


def get_stats(
    root_dir: Path,
    *,
    feature: str | None = None,
    doc_type: str | None = None,
    date: str | None = None,
) -> dict:
    """Compute vault statistics with optional filters.

    Returns dict with: total_docs, total_features, counts_by_type,
    orphaned_count, invalid_link_count.
    """
    docs = list_documents(root_dir, feature=feature, doc_type=doc_type, date=date)

    counts_by_type: dict[str, int] = {}
    features: set[str] = set()
    for d in docs:
        counts_by_type[d.doc_type] = counts_by_type.get(d.doc_type, 0) + 1
        if d.feature:
            features.add(d.feature)

    # Orphan/invalid counts from graph (unfiltered)
    from ..graph import VaultGraph

    try:
        graph = VaultGraph(root_dir)
        orphaned_count = len(graph.get_orphaned())
        invalid_link_count = len(graph.get_invalid_links())
    except Exception:
        orphaned_count = 0
        invalid_link_count = 0

    return {
        "total_docs": len(docs),
        "total_features": len(features),
        "counts_by_type": counts_by_type,
        "orphaned_count": orphaned_count,
        "invalid_link_count": invalid_link_count,
    }


def list_feature_details(
    root_dir: Path,
    *,
    date: str | None = None,
    doc_type: str | None = None,
    orphaned_only: bool = False,
) -> list[dict]:
    """List features with enriched metadata.

    Returns list of dicts with: name, doc_count, types (set of doc types
    present), earliest_date, has_plan.
    """
    docs = _scan_all(root_dir)

    # Group by feature
    by_feature: dict[str, list[VaultDocument]] = {}
    for d in docs:
        if d.feature:
            by_feature.setdefault(d.feature, []).append(d)

    # Orphan detection
    orphan_features: set[str] = set()
    if orphaned_only:
        from ..graph import VaultGraph

        graph = VaultGraph(root_dir)
        orphan_names = set(graph.get_orphaned())
        for feat, feat_docs in by_feature.items():
            if all(d.name in orphan_names for d in feat_docs):
                orphan_features.add(feat)

    results = []
    for feat, feat_docs in sorted(by_feature.items()):
        if orphaned_only and feat not in orphan_features:
            continue

        types = {d.doc_type for d in feat_docs}

        if doc_type and doc_type not in types:
            continue

        dates = [d.date for d in feat_docs if d.date]
        earliest = min(dates) if dates else None

        if date and earliest and earliest > date:
            continue

        results.append(
            {
                "name": feat,
                "doc_count": len(feat_docs),
                "types": sorted(types),
                "earliest_date": earliest,
                "has_plan": "plan" in types,
            }
        )

    return results


def archive_feature(root_dir: Path, feature: str) -> dict:
    """Move all documents for a feature into .vault/_archive/.

    Preserves directory structure under the archive folder.

    Returns dict with: archived_count, paths (list of new paths).
    """
    import shutil

    from ..config import get_config

    cfg = get_config()
    vault_dir = root_dir / cfg.docs_dir
    archive_dir = vault_dir / "_archive"

    feature = feature.lstrip("#")
    docs = list_documents(root_dir, feature=feature)

    if not docs:
        return {"archived_count": 0, "paths": []}

    archived: list[str] = []
    for doc in docs:
        # Preserve subdirectory (e.g., adr/, plan/)
        rel = doc.path.relative_to(vault_dir)
        dest = archive_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(doc.path), str(dest))
        archived.append(str(dest.relative_to(root_dir)))

    return {"archived_count": len(archived), "paths": archived}

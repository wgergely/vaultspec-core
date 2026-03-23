"""Generate and update feature index documents.

A feature index is a living ``<feature>.index.md`` file in the vault root
that makes the implicit feature-tag binding explicit in the document graph.
It lists all documents sharing a feature tag and links to them via
``related:`` frontmatter.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from ..graph.api import DocNode

logger = logging.getLogger(__name__)

__all__ = ["generate_feature_index"]


def generate_feature_index(
    root_dir: Path,
    feature: str,
    *,
    nodes: list[DocNode],
    date_str: str | None = None,
) -> Path:
    """Create or update a feature index file for *feature*.

    The index file lives at ``<docs_dir>/<feature>.index.md`` and contains
    a ``related:`` field linking to every document tagged with the feature,
    plus a body listing documents grouped by type.

    Args:
        root_dir: Project root directory.
        feature: Feature name (without ``#`` prefix).
        nodes: Pre-fetched list of :class:`~vaultspec_core.graph.api.DocNode`
            for this feature (from :meth:`VaultGraph.get_feature_nodes`).
        date_str: Override date for the index. Defaults to today.

    Returns:
        Path to the created or updated index file.
    """
    from ..config import get_config

    docs_dir = root_dir / get_config().docs_dir
    index_path = docs_dir / f"{feature}.index.md"
    date = date_str or datetime.now().strftime("%Y-%m-%d")

    # Build related links from all feature nodes (excluding self)
    related_links: list[str] = []
    for node in nodes:
        if node.path and not node.name.endswith(".index"):
            related_links.append(f"[[{node.name}]]")

    # Build body document list grouped by type
    by_type: dict[str, list[DocNode]] = {}
    for node in nodes:
        if node.path and not node.name.endswith(".index"):
            dt_key = node.doc_type.value if node.doc_type else "unknown"
            by_type.setdefault(dt_key, []).append(node)

    body_lines: list[str] = []
    for type_name in sorted(by_type):
        body_lines.append(f"### {type_name}")
        body_lines.append("")
        for node in sorted(by_type[type_name], key=lambda n: (n.date or "", n.name)):
            title = node.title or node.name
            body_lines.append(f"- `{node.name}` - {title}")
        body_lines.append("")

    document_list = "\n".join(body_lines).rstrip()

    # Build related YAML block
    if related_links:
        related_yaml = "\n".join(f"  - '{link}'" for link in sorted(related_links))
        related_block = f"related:\n{related_yaml}"
    else:
        related_block = "related: []"

    content = (
        f"---\n"
        f"generated: true\n"
        f"tags:\n"
        f"  - '#{feature}'\n"
        f"date: '{date}'\n"
        f"{related_block}\n"
        f"---\n"
        f"\n"
        f"# `{feature}` feature index\n"
        f"\n"
        f"Auto-generated index of all documents tagged with `#{feature}`.\n"
        f"\n"
        f"## Documents\n"
        f"\n"
        f"{document_list}\n"
    )

    docs_dir.mkdir(parents=True, exist_ok=True)
    index_path.write_text(content, encoding="utf-8")
    logger.info("Generated feature index: %s", index_path)
    return index_path

"""Vault document graph: builds and queries a bidirectional wiki-link graph."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..vaultcore import (
    DocType,
    extract_related_links,
    extract_wiki_links,
    get_doc_type,
    parse_vault_metadata,
    scan_vault,
)

if TYPE_CHECKING:
    import pathlib

logger = logging.getLogger(__name__)

__all__ = ["DocNode", "VaultGraph"]


@dataclass
class DocNode:
    """A node in the vault document graph representing a single document.

    Attributes:
        path: Filesystem path to the document file.
        name: Document stem (filename without extension), used as the graph key.
        doc_type: Categorised document type derived from vault folder location.
        tags: Set of frontmatter tags extracted from the document.
        out_links: Names of documents this document links to (outgoing edges).
        in_links: Names of documents that link to this document (incoming edges).
    """

    path: pathlib.Path
    name: str
    doc_type: DocType | None = None
    tags: set[str] = field(default_factory=set)
    out_links: set[str] = field(default_factory=set)
    in_links: set[str] = field(default_factory=set)


class VaultGraph:
    """Directed graph of vault documents linked by wiki-links and related fields.

    Scans ``root_dir`` on construction, building a bidirectional link graph
    where each :class:`DocNode` records its outgoing and incoming wiki-link
    edges.  Query methods expose hotspot analysis, feature rankings, orphan
    detection, and broken-link discovery.
    """

    def __init__(self, root_dir: pathlib.Path) -> None:
        """Initialise the graph by scanning and building from ``root_dir``.

        Args:
            root_dir: Root directory of the vault to analyse.
        """
        self.root_dir = root_dir
        self.nodes: dict[str, DocNode] = {}
        self._build_graph()

    def _build_graph(self) -> None:
        """Scan the vault and populate ``self.nodes`` with link edges.

        Performs two passes: the first creates :class:`DocNode` instances with
        metadata; the second extracts wiki-links and populates ``out_links``
        and ``in_links`` on each node.
        """
        logger.info("Building vault graph from %s", self.root_dir)

        # First pass: Create nodes with metadata
        for path in scan_vault(self.root_dir):
            name = path.stem
            doc_type = get_doc_type(path, self.root_dir)

            node = DocNode(path=path, name=name, doc_type=doc_type)

            try:
                content = path.read_text(encoding="utf-8")
                metadata, _body = parse_vault_metadata(content)
                node.tags = set(metadata.tags)
            except (OSError, UnicodeDecodeError) as e:
                logger.warning("Failed to read metadata from %s: %s", path, e)

            self.nodes[name] = node

        logger.info("Graph pass 1: created %d nodes", len(self.nodes))

        # Second pass: Extract links
        for name, node in self.nodes.items():
            try:
                content = node.path.read_text(encoding="utf-8")
                metadata, body = parse_vault_metadata(content)

                links = extract_wiki_links(body)
                links.update(extract_related_links(metadata.related))

                node.out_links = links

                for target in links:
                    if target in self.nodes:
                        self.nodes[target].in_links.add(name)
            except (OSError, UnicodeDecodeError) as e:
                logger.warning("Failed to extract links from %s: %s", node.path, e)

        logger.info("Graph build complete: %d nodes with links", len(self.nodes))

    def get_hotspots(
        self,
        limit: int = 10,
        doc_type: DocType | None = None,
        feature: str | None = None,
    ) -> list[tuple[str, int]]:
        """Return documents with the most incoming links, with optional filtering.

        Args:
            limit: Maximum number of results to return.
            doc_type: When provided, restrict results to this document type.
            feature: When provided, restrict results to documents tagged with
                this feature (``#``-prefix is added automatically if absent).

        Returns:
            List of ``(name, in_link_count)`` tuples, sorted descending by
            in-link count, truncated to ``limit``.
        """
        filtered_nodes = list(self.nodes.values())

        if doc_type:
            filtered_nodes = [n for n in filtered_nodes if n.doc_type == doc_type]

        if feature:
            tag = f"#{feature}" if not feature.startswith("#") else feature
            filtered_nodes = [n for n in filtered_nodes if tag in n.tags]

        rankings = [(node.name, len(node.in_links)) for node in filtered_nodes]
        return sorted(rankings, key=lambda x: x[1], reverse=True)[:limit]

    def get_feature_rankings(self, limit: int = 10) -> list[tuple[str, int]]:
        """Rank features by total incoming links to their documents.

        Aggregates ``in_links`` counts across all nodes that share a non-type
        tag (i.e., a feature tag).

        Args:
            limit: Maximum number of features to return.

        Returns:
            List of ``(feature_name, total_in_links)`` tuples, sorted
            descending by score, truncated to ``limit``.
        """
        feature_scores: dict[str, int] = {}

        for node in self.nodes.values():
            # Sum up in-links for each feature tag this doc has
            score = len(node.in_links)
            for tag in node.tags:
                if not DocType.from_tag(tag):
                    f_name = tag.lstrip("#")
                    feature_scores[f_name] = feature_scores.get(f_name, 0) + score

        rankings = list(feature_scores.items())
        return sorted(rankings, key=lambda x: x[1], reverse=True)[:limit]

    def get_orphaned(self) -> list[str]:
        """Return documents with no incoming links (and not index-like).

        Returns:
            List of document names that have no in-links, excluding any node
            whose name is ``readme`` (case-insensitive).
        """
        return [
            name
            for name, node in self.nodes.items()
            if not node.in_links and name.lower() != "readme"
        ]

    def get_invalid_links(self) -> list[tuple[str, str]]:
        """Return ``(source, target)`` pairs for links that don't exist in the vault.

        Returns:
            List of ``(source_name, target_name)`` tuples where the target
            document is not present in the graph.
        """
        invalid = []
        for name, node in self.nodes.items():
            for target in node.out_links:
                if target not in self.nodes:
                    invalid.append((name, target))
        return invalid

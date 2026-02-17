from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from vault.links import extract_related_links, extract_wiki_links
from vault.models import DocType
from vault.parser import parse_vault_metadata
from vault.scanner import get_doc_type, scan_vault

if TYPE_CHECKING:
    import pathlib

logger = logging.getLogger(__name__)


@dataclass
class DocNode:
    """A node in the vault document graph representing a single document."""

    path: pathlib.Path
    name: str
    doc_type: DocType | None = None
    tags: set[str] = field(default_factory=set)
    out_links: set[str] = field(default_factory=set)
    in_links: set[str] = field(default_factory=set)


class VaultGraph:
    """Directed graph of vault documents linked by wiki-links and related fields."""

    def __init__(self, root_dir: pathlib.Path) -> None:
        self.root_dir = root_dir
        self.nodes: dict[str, DocNode] = {}
        self._build_graph()

    def _build_graph(self) -> None:
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
        """Returns documents with the most incoming links, with optional filtering."""
        filtered_nodes = list(self.nodes.values())

        if doc_type:
            filtered_nodes = [n for n in filtered_nodes if n.doc_type == doc_type]

        if feature:
            tag = f"#{feature}" if not feature.startswith("#") else feature
            filtered_nodes = [n for n in filtered_nodes if tag in n.tags]

        rankings = [(node.name, len(node.in_links)) for node in filtered_nodes]
        return sorted(rankings, key=lambda x: x[1], reverse=True)[:limit]

    def get_feature_rankings(self, limit: int = 10) -> list[tuple[str, int]]:
        """Rank features by total incoming links to their documents."""
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
        """Returns documents with no incoming links (and not index-like)."""
        return [
            name
            for name, node in self.nodes.items()
            if not node.in_links and name.lower() != "readme"
        ]

    def get_invalid_links(self) -> list[tuple[str, str]]:
        """Returns (source, target) for links that don't exist in the vault."""
        invalid = []
        for name, node in self.nodes.items():
            for target in node.out_links:
                if target not in self.nodes:
                    invalid.append((name, target))
        return invalid

"""Retrieval pipeline for vault semantic search.

Implements query parsing, hybrid search, and graph-aware re-ranking.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pathlib

    from graph.api import VaultGraph
    from rag.embeddings import EmbeddingModel
    from rag.store import VaultStore

logger = logging.getLogger(__name__)

# Filter token patterns: type:adr, feature:rag, date:2026-02, tag:#research
_FILTER_PATTERN = re.compile(r"\b(type|feature|date|tag):(\S+)")

# Map filter keys to store column names
_FILTER_KEY_MAP = {
    "type": "doc_type",
    "feature": "feature",
    "date": "date",
}


@dataclass
class ParsedQuery:
    """A parsed search query with extracted metadata filters."""

    text: str  # natural language portion
    filters: dict[str, str]  # extracted metadata filters


@dataclass
class SearchResult:
    """A single search result from the vault."""

    id: str
    path: str
    title: str
    doc_type: str
    feature: str
    date: str
    score: float
    snippet: str  # first 200 chars of content


def parse_query(raw_query: str) -> ParsedQuery:
    """Parse a raw query string into text and metadata filters.

    Extracts filter tokens (type:adr, feature:rag, date:2026-02, tag:#research)
    and returns the remaining text as the natural language query.

    Examples::

        "type:adr feature:rag vector database"
        -> ParsedQuery(text="vector database",
                       filters={"doc_type": "adr", "feature": "rag"})

        "vector database"
        -> ParsedQuery(text="vector database", filters={})
    """
    filters: dict[str, str] = {}

    for match in _FILTER_PATTERN.finditer(raw_query):
        key = match.group(1)
        value = match.group(2)

        if key == "tag":
            # tag: filter is not a direct column filter, handled separately
            # Store it for potential graph re-ranking use
            filters["tag"] = value.lstrip("#")
        elif key in _FILTER_KEY_MAP:
            filters[_FILTER_KEY_MAP[key]] = value

    # Remove filter tokens from the query text
    text = _FILTER_PATTERN.sub("", raw_query).strip()
    # Collapse multiple spaces
    text = re.sub(r"\s+", " ", text)

    return ParsedQuery(text=text, filters=filters)


def rerank_with_graph(
    results: list[SearchResult],
    root_dir: pathlib.Path,
    query: ParsedQuery,
    graph: VaultGraph | None = None,
) -> list[SearchResult]:
    """Apply graph-aware score boosts to search results.

    Uses the existing VaultGraph API for:
    - Authority boost: high in-link count documents get score multiplier
    - Neighborhood boost: docs sharing feature with query filter get boost
    - Recency boost: more recent documents get mild boost

    Args:
        results: Search results to re-rank.
        root_dir: Path to vault root (used if graph is None).
        query: Parsed query with filters.
        graph: Optional pre-built VaultGraph. If None, one is constructed.
    """
    if graph is None:
        from graph.api import VaultGraph as _VaultGraph

        try:
            graph = _VaultGraph(root_dir)
        except Exception as e:
            logger.error("Search failed: %s", e, exc_info=True)
            return results

    for result in results:
        node = graph.nodes.get(result.id)
        if node is None:
            continue

        # Authority boost: score *= (1 + 0.1 * min(in_link_count, 10))
        in_link_count = len(node.in_links)
        result.score *= 1 + 0.1 * min(in_link_count, 10)

        # Neighborhood boost: if query has a feature filter, boost docs
        # whose wiki-link neighbors share that feature tag
        feature_filter = query.filters.get("feature")
        if feature_filter:
            feature_tag = f"#{feature_filter}"
            neighbor_has_feature = False
            for neighbor_name in node.out_links | node.in_links:
                neighbor = graph.nodes.get(neighbor_name)
                if neighbor and feature_tag in neighbor.tags:
                    neighbor_has_feature = True
                    break
            if neighbor_has_feature:
                result.score *= 1.15

    # Recency boost: sort by date descending, most recent gets highest rank
    dated = [(r, r.date) for r in results]
    dated.sort(key=lambda x: x[1], reverse=True)
    for rank, (result, _) in enumerate(dated):
        result.score *= 1 + 0.02 * (len(dated) - rank)

    # Re-sort by adjusted score
    results.sort(key=lambda r: r.score, reverse=True)
    return results


class VaultSearcher:
    """Orchestrates vault semantic search with hybrid retrieval and re-ranking."""

    def __init__(
        self,
        root_dir: pathlib.Path,
        model: EmbeddingModel,
        store: VaultStore,
        *,
        graph_ttl_seconds: float | None = None,
    ) -> None:
        if graph_ttl_seconds is None:
            from core.config import get_config

            graph_ttl_seconds = get_config().graph_ttl_seconds
        self.root_dir = root_dir
        self.model = model
        self.store = store
        self._graph_ttl = graph_ttl_seconds
        self._cached_graph: VaultGraph | None = None
        self._graph_built_at: float = 0.0

    def _get_graph(self) -> VaultGraph | None:
        """Return a cached VaultGraph, rebuilding if TTL expired."""
        from graph.api import VaultGraph as _VaultGraph

        now = time.monotonic()
        if self._cached_graph is None or (now - self._graph_built_at) > self._graph_ttl:
            try:
                self._cached_graph = _VaultGraph(self.root_dir)
                self._graph_built_at = now
            except Exception as e:
                logger.error("Search failed: %s", e, exc_info=True)
                return None
        return self._cached_graph

    def search(self, raw_query: str, top_k: int = 5) -> list[SearchResult]:
        """Execute a full search pipeline: parse, embed, search, re-rank.

        Args:
            raw_query: Natural language query with optional filter tokens.
            top_k: Number of results to return.

        Returns:
            List of SearchResult sorted by relevance score.
        """
        parsed = parse_query(raw_query)

        # Encode query
        query_vector = self.model.encode_query(
            parsed.text if parsed.text else raw_query
        )

        # Build store-level filters (exclude 'tag' which isn't a column)
        store_filters = {k: v for k, v in parsed.filters.items() if k != "tag"}

        # Execute hybrid search, requesting more than top_k for re-ranking
        fetch_limit = min(top_k * 3, 50)
        raw_results = self.store.hybrid_search(
            query_vector=query_vector,
            query_text=parsed.text if parsed.text else raw_query,
            filters=store_filters if store_filters else None,
            limit=fetch_limit,
        )

        # Build SearchResult list
        results = []
        for r in raw_results:
            score = r.get("_relevance_score", r.get("_distance", 0.0))
            # Normalize: _distance is inverse (lower = better), _relevance_score
            # is direct (higher = better). If using _distance, invert it.
            if "_relevance_score" not in r and "_distance" in r:
                dist = r["_distance"]
                score = 1.0 / (1.0 + dist) if dist >= 0 else 0.0

            content = r.get("content", "")
            snippet = content[:200].strip() if content else ""

            results.append(
                SearchResult(
                    id=r["id"],
                    path=r["path"],
                    title=r.get("title", ""),
                    doc_type=r.get("doc_type", ""),
                    feature=r.get("feature", ""),
                    date=r.get("date", ""),
                    score=float(score),
                    snippet=snippet,
                )
            )

        # Apply graph-aware re-ranking with cached graph
        graph = self._get_graph()
        results = rerank_with_graph(results, self.root_dir, parsed, graph=graph)

        return results[:top_k]

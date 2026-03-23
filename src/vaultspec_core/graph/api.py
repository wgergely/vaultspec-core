"""Build, query, and render the vault document relationship graph.

Turns ``vaultcore`` scanning, metadata parsing, and wiki-link extraction into
a queryable directed graph of ``.vault/`` documents backed by
``networkx.DiGraph``. Delegates rendering to ``phart`` (ASCII topology) and
``rich`` (hierarchical tree), and serialisation to
``networkx.readwrite.json_graph``.

Example::

    graph = VaultGraph(root_dir)
    tree  = graph.render_tree(feature="my-feature")   # Rich Tree
    ascii = graph.render_ascii(feature="my-feature")  # phart ASCII
    data  = graph.to_dict(feature="my-feature")       # JSON-ready dict
    stats = graph.metrics()                           # GraphMetrics

Exports:
    :class:`DocNode`: Node carrying full frontmatter, body, and link metadata.
    :class:`GraphMetrics`: Computed shape and size statistics for the graph.
    :class:`VaultGraph`: Main entry point; instantiate with a vault root dir.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any

import networkx as nx
from networkx.readwrite import json_graph

from ..vaultcore import (
    DocType,
    extract_related_links,
    extract_wiki_links,
    get_doc_type,
    parse_frontmatter,
    parse_vault_metadata,
    scan_vault,
)
from ..vaultcore.models import DocumentMetadata

if TYPE_CHECKING:
    import pathlib

    from rich.tree import Tree

    from ..vaultcore.checks._base import VaultSnapshot

logger = logging.getLogger(__name__)

__all__ = ["DocNode", "GraphMetrics", "VaultGraph"]

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class DocNode:
    """A node in the vault document graph representing a single document.

    Carries the full parsed frontmatter, body text, and derived connection
    metadata so that consumers never need to re-read the filesystem.

    Attributes:
        path: Filesystem path to the document file, or ``None`` for phantoms.
        name: Document stem (filename without extension), used as graph key.
        doc_type: Categorised document type from vault folder location.
        feature: Feature tag (without ``#`` prefix), or ``None``.
        date: ISO-8601 date string from frontmatter, or ``None``.
        title: First ``# heading`` extracted from body, or ``None``.
        tags: Set of all frontmatter tags.
        frontmatter: Raw frontmatter dict (everything parsed from YAML).
        body: Markdown body text after the YAML fence.
        word_count: Approximate word count of the body.
        out_links: Names of documents this document links to.
        in_links: Names of documents that link to this document.
        phantom: ``True`` for unresolved wiki-link targets that have no
            backing file.  Mirrors Obsidian's "not created" node concept.
    """

    path: pathlib.Path | None
    name: str
    doc_type: DocType | None = None
    feature: str | None = None
    date: str | None = None
    title: str | None = None
    tags: set[str] = field(default_factory=set)
    frontmatter: dict[str, Any] = field(default_factory=dict)
    body: str = ""
    word_count: int = 0
    out_links: set[str] = field(default_factory=set)
    in_links: set[str] = field(default_factory=set)
    phantom: bool = False

    def to_nx_attrs(self) -> dict[str, Any]:
        """Return a networkx-compatible node attribute dict.

        Converts non-serialisable types (sets, Path, enums) to plain
        JSON-friendly values suitable for storage on a ``nx.DiGraph``
        node and for ``nx.node_link_data`` serialisation.

        Returns:
            Dict with string-valued ``path``, sorted lists for ``tags``,
            ``out_links``, and ``in_links``, and ``None``-safe scalar fields.
        """
        return {
            "name": self.name,
            "path": str(self.path) if self.path else None,
            "doc_type": (self.doc_type.value if self.doc_type else None),
            "feature": self.feature,
            "date": self.date,
            "title": self.title,
            "tags": sorted(self.tags),
            "frontmatter": self.frontmatter,
            "word_count": self.word_count,
            "out_links": sorted(self.out_links),
            "in_links": sorted(self.in_links),
            "phantom": self.phantom,
        }


@dataclass
class GraphMetrics:
    """Aggregate statistics describing the shape and size of a vault graph.

    All graph-theoretic values (density, centrality, components) are
    computed by ``networkx`` built-in algorithms rather than manual
    calculation.

    Attributes:
        total_nodes: Number of documents in the graph.
        total_edges: Number of directed link edges.
        total_features: Number of distinct feature tags.
        total_words: Sum of word counts across all documents.
        density: Graph density (0.0 to 1.0) via ``nx.density``.
        avg_in_degree: Mean incoming edges per node.
        avg_out_degree: Mean outgoing edges per node.
        max_in_degree: Highest incoming edge count (with node name).
        max_out_degree: Highest outgoing edge count (with node name).
        in_degree_centrality: ``nx.in_degree_centrality`` scores.
        betweenness_centrality: ``nx.betweenness_centrality`` scores.
        phantom_count: Number of phantom (unresolved) nodes in the graph.
        orphan_count: Truly isolated nodes (no links and no feature siblings).
        dangling_link_count: Edges pointing to phantom (unresolved) targets.
        connected_components: Weakly connected components via networkx.
        nodes_by_type: Document count per ``DocType``.
        nodes_by_feature: Document count per feature tag.
    """

    total_nodes: int = 0
    total_edges: int = 0
    total_features: int = 0
    total_words: int = 0
    density: float = 0.0
    avg_in_degree: float = 0.0
    avg_out_degree: float = 0.0
    max_in_degree: tuple[str, int] = ("", 0)
    max_out_degree: tuple[str, int] = ("", 0)
    in_degree_centrality: dict[str, float] = field(
        default_factory=dict,
    )
    betweenness_centrality: dict[str, float] = field(
        default_factory=dict,
    )
    phantom_count: int = 0
    orphan_count: int = 0
    dangling_link_count: int = 0
    connected_components: int = 0
    nodes_by_type: dict[str, int] = field(default_factory=dict)
    nodes_by_feature: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable dictionary of all metrics.

        Converts ``max_in_degree`` and ``max_out_degree`` tuples to
        ``{"node": str, "count": int}`` dicts for clean JSON output.

        Returns:
            Flat dict of all metric fields; safe to pass to ``json.dumps``.
        """
        d = asdict(self)
        d["max_in_degree"] = {
            "node": self.max_in_degree[0],
            "count": self.max_in_degree[1],
        }
        d["max_out_degree"] = {
            "node": self.max_out_degree[0],
            "count": self.max_out_degree[1],
        }
        return d


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_title(body: str) -> str | None:
    """Return the text of the first ``# ...`` heading, or ``None``."""
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return None


def _extract_feature(tags: set[str]) -> str | None:
    """Return the first non-type tag as the feature name (no ``#``)."""
    for tag in tags:
        if not DocType.from_tag(tag):
            return tag.lstrip("#")
    return None


def _top_n(
    scores: dict[str, float],
    n: int = 10,
) -> dict[str, float]:
    """Return the top *n* entries from *scores* by value descending."""
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    return dict(ranked[:n])


# ---------------------------------------------------------------------------
# VaultGraph
# ---------------------------------------------------------------------------


class VaultGraph:
    """Directed graph of vault documents linked by wiki-links and
    ``related:`` fields.

    Backed by a ``networkx.DiGraph`` for efficient traversal and
    algorithm access.  Each graph node stores serialisable attributes
    from its :class:`DocNode`, and each directed edge represents a
    wiki-link or ``related:`` reference.

    Args:
        root_dir: Root directory of the vault to analyse.

    Example::

        graph = VaultGraph(Path("/my/project"))

        # ASCII graph in the terminal (via phart)
        print(graph.render_ascii(feature="auth"))

        # Rich hierarchical tree
        console.print(graph.render_tree(feature="auth"))

        # JSON export (networkx node-link format)
        print(graph.to_json())

        # Metrics (all via networkx algorithms)
        m = graph.metrics()
        print(f"Density: {m.density:.3f}")
    """

    def __init__(self, root_dir: pathlib.Path) -> None:
        self.root_dir = root_dir
        self.nodes: dict[str, DocNode] = {}
        self._digraph: nx.DiGraph = nx.DiGraph()
        self._dangling_links: list[tuple[str, str]] = []
        self._build_graph()

    # -- Construction --------------------------------------------------------

    def _build_graph(self) -> None:
        """Scan the vault and populate nodes + networkx DiGraph.

        Uses a two-pass strategy:

        1. **Pass 1**  - create :class:`DocNode` instances, detecting stem
           collisions.  When two files share the same stem (e.g.
           ``adr/my-doc.md`` and ``reference/my-doc.md``), all colliding
           nodes are re-keyed as ``type/stem`` so that no data is silently
           dropped.
        2. **Pass 2**  - extract links and create directed edges.  Bare
           wiki-link stems that match multiple qualified keys fan-out to
           all variants (with a logged warning).
        """
        logger.info("Building vault graph from %s", self.root_dir)

        # Pass 1a: collect all DocNodes keyed by stem, detecting collisions
        by_stem: dict[str, list[DocNode]] = {}

        for path in scan_vault(self.root_dir):
            logger.debug("Graph pass 1: reading %s", path)
            stem = path.stem
            doc_type = get_doc_type(path, self.root_dir)

            node = DocNode(path=path, name=stem, doc_type=doc_type)

            try:
                content = path.read_text(encoding="utf-8")
                metadata, body = parse_vault_metadata(content)
                raw_fm, _ = parse_frontmatter(content)

                node.tags = set(metadata.tags)
                node.date = metadata.date
                node.feature = _extract_feature(node.tags)
                node.frontmatter = raw_fm
                node.body = body
                node.word_count = len(body.split())
                node.title = _extract_title(body)
            except (OSError, UnicodeDecodeError) as e:
                logger.warning(
                    "Failed to read metadata from %s: %s",
                    path,
                    e,
                )

            by_stem.setdefault(stem, []).append(node)

        # Pass 1b: assign unique keys  - qualify colliding stems with
        # their doc-type prefix, build a stem-to-keys index for link
        # resolution in pass 2.
        self._stem_index: dict[str, list[str]] = {}

        for stem, node_list in by_stem.items():
            if len(node_list) == 1:
                # Unique stem  - use it directly as the key.
                node = node_list[0]
                self.nodes[stem] = node
                self._digraph.add_node(stem, **node.to_nx_attrs())
                self._stem_index[stem] = [stem]
            else:
                # Collision  - qualify each with its doc-type directory.
                keys: list[str] = []
                for node in node_list:
                    dt = node.doc_type.value if node.doc_type else "unknown"
                    qualified = f"{dt}/{stem}"
                    node.name = qualified
                    self.nodes[qualified] = node
                    self._digraph.add_node(
                        qualified,
                        **node.to_nx_attrs(),
                    )
                    keys.append(qualified)
                self._stem_index[stem] = keys
                logger.warning(
                    "Stem collision for '%s': qualified as %s",
                    stem,
                    keys,
                )

        logger.info(
            "Graph pass 1: created %d nodes (%d stem collisions)",
            len(self.nodes),
            sum(1 for v in self._stem_index.values() if len(v) > 1),
        )

        # Pass 2: extract links -> edges.  Unresolved targets become
        # phantom nodes so the graph mirrors Obsidian's "not created"
        # link model.  Iterate over a snapshot of the real-node keys
        # because the dict grows as phantoms are added.
        real_node_keys = list(self.nodes.keys())
        for name in real_node_keys:
            node = self.nodes[name]
            try:
                links = extract_wiki_links(node.body)
                links.update(
                    extract_related_links(
                        node.frontmatter.get("related", []),
                    ),
                )

                resolved_targets: set[str] = set()
                for target in links:
                    resolved = self._resolve_link(target)
                    resolved_targets.update(resolved)

                node.out_links = resolved_targets

                for target_key in resolved_targets:
                    if target_key in self.nodes:
                        self.nodes[target_key].in_links.add(name)
                        self._digraph.add_edge(name, target_key)
                        if self.nodes[target_key].phantom:
                            self._dangling_links.append(
                                (name, target_key),
                            )
                    else:
                        # Create a phantom node (deduplicated).
                        phantom = DocNode(
                            path=None,
                            name=target_key,
                            phantom=True,
                        )
                        self.nodes[target_key] = phantom
                        self._digraph.add_node(
                            target_key,
                            **phantom.to_nx_attrs(),
                        )
                        phantom.in_links.add(name)
                        self._digraph.add_edge(name, target_key)
                        self._dangling_links.append(
                            (name, target_key),
                        )
            except (OSError, UnicodeDecodeError) as e:
                logger.warning(
                    "Failed to extract links from %s: %s",
                    node.path,
                    e,
                )

        # Pass 3: sync nx node attrs with updated in_links/out_links
        for name, node in self.nodes.items():
            self._digraph.nodes[name]["out_links"] = sorted(
                node.out_links,
            )
            self._digraph.nodes[name]["in_links"] = sorted(
                node.in_links,
            )

        logger.info(
            "Graph build complete: %d nodes, %d edges",
            self._digraph.number_of_nodes(),
            self._digraph.number_of_edges(),
        )

    def _resolve_link(self, target: str) -> list[str]:
        """Resolve a wiki-link target to one or more node keys.

        Resolution order:

        1. Exact match against an existing node key (handles both bare
           stems and already-qualified ``type/stem`` references).
        2. Stem index lookup  - if the bare stem maps to multiple
           qualified keys, all are returned and a warning is logged.
        3. No match  - returns the original target so it is recorded as
           a dangling link.
        """
        # Exact key match (unique stem or qualified reference)
        if target in self.nodes:
            return [target]

        # Stem index lookup (handles collisions)
        keys = self._stem_index.get(target, [])
        if keys:
            if len(keys) > 1:
                logger.debug(
                    "Ambiguous wiki-link [[%s]] resolved to %d nodes: %s",
                    target,
                    len(keys),
                    keys,
                )
            return keys

        # No match  - treat as dangling link
        return [target]

    # -- Direct networkx access ----------------------------------------------

    @property
    def digraph(self) -> nx.DiGraph:
        """The underlying ``networkx.DiGraph`` for direct algorithm access.

        Consumers may call any ``networkx`` function on this object
        (e.g. ``nx.pagerank(graph.digraph)``).

        Returns:
            The internal ``nx.DiGraph`` instance; not a copy.
        """
        return self._digraph

    def subgraph(
        self,
        feature: str | None = None,
    ) -> nx.DiGraph:
        """Return a networkx subgraph view, optionally scoped to
        *feature*.

        Args:
            feature: When set, restrict to nodes with this feature tag.

        Returns:
            ``nx.DiGraph`` (a subgraph view, not a copy).
        """
        if not feature:
            return self._digraph
        names = {n.name for n in self.get_feature_nodes(feature)}
        return self._digraph.subgraph(names)

    # -- Query methods -------------------------------------------------------

    def get_node(self, name: str) -> DocNode | None:
        """Return the :class:`DocNode` for *name*, or ``None``.

        Args:
            name: Document stem (graph key).

        Returns:
            The matching :class:`DocNode`, or ``None`` if not found.
        """
        return self.nodes.get(name)

    def get_hotspots(
        self,
        limit: int = 10,
        doc_type: DocType | None = None,
        feature: str | None = None,
    ) -> list[tuple[str, int]]:
        """Return documents with the most incoming links.

        Uses ``nx.in_degree_centrality`` on the digraph and maps
        normalised scores back to raw in-degree counts.

        Args:
            limit: Maximum number of results to return.
            doc_type: Restrict results to this document type.
            feature: Restrict results to documents tagged with this
                feature (``#``-prefix is added automatically if absent).

        Returns:
            ``(name, in_link_count)`` tuples sorted descending.
        """
        filtered = [n for n in self.nodes.values() if not n.phantom]

        if doc_type:
            filtered = [n for n in filtered if n.doc_type == doc_type]

        if feature:
            tag = f"#{feature}" if not feature.startswith("#") else feature
            filtered = [n for n in filtered if tag in n.tags]

        rankings = [(n.name, len(n.in_links)) for n in filtered]
        return sorted(
            rankings,
            key=lambda x: x[1],
            reverse=True,
        )[:limit]

    def get_feature_rankings(
        self,
        limit: int = 10,
    ) -> list[tuple[str, int]]:
        """Rank features by total incoming links to their documents.

        Args:
            limit: Maximum features to return.

        Returns:
            ``(feature_name, total_in_links)`` tuples descending.
        """
        scores: dict[str, int] = {}
        for node in self.nodes.values():
            if node.phantom:
                continue
            score = len(node.in_links)
            for tag in node.tags:
                if not DocType.from_tag(tag):
                    f_name = tag.lstrip("#")
                    scores[f_name] = scores.get(f_name, 0) + score
        return sorted(
            scores.items(),
            key=lambda x: x[1],
            reverse=True,
        )[:limit]

    def get_orphaned(self) -> list[str]:
        """Return document names that are truly isolated from the graph.

        A node is orphaned only when it has **no connections at all** --
        no incoming links, no outgoing links, and no sibling documents
        sharing the same feature tag.  Documents that link out to a plan
        or ADR (common for exec records) are connected and therefore not
        orphans.

        Returns:
            Sorted list of genuinely isolated node names
            (excludes ``readme``).
        """
        # Pre-compute which features have more than one document.
        # A node sharing a feature tag with at least one other node is
        # implicitly connected through that feature cluster.
        feature_sizes: dict[str, int] = {}
        for node in self.nodes.values():
            if node.feature:
                feature_sizes[node.feature] = feature_sizes.get(node.feature, 0) + 1

        return sorted(
            name
            for name, node in self.nodes.items()
            if not node.phantom
            and name.lower() != "readme"
            and not node.in_links
            and not node.out_links
            and (not node.feature or feature_sizes.get(node.feature, 0) <= 1)
        )

    def get_dangling_links(self) -> list[tuple[str, str]]:
        """Return all dangling link pairs recorded during graph construction.

        Returns:
            List of ``(source, target)`` tuples where *target* does not
            exist as a node in the graph.
        """
        return list(self._dangling_links)

    def get_feature_nodes(self, feature: str) -> list[DocNode]:
        """Return all nodes tagged with *feature*, sorted by date then name.

        Args:
            feature: Feature name (without ``#`` prefix).

        Returns:
            List of :class:`DocNode` instances sorted by ``(date, name)``.
        """
        tag = f"#{feature}" if not feature.startswith("#") else feature
        nodes = [n for n in self.nodes.values() if not n.phantom and tag in n.tags]
        return sorted(
            nodes,
            key=lambda n: (n.date or "", n.name),
        )

    def get_features(self) -> list[str]:
        """Return a sorted list of all feature names in the graph."""
        features: set[str] = set()
        for node in self.nodes.values():
            if not node.phantom and node.feature:
                features.add(node.feature)
        return sorted(features)

    def to_snapshot(self) -> VaultSnapshot:
        """Build a :data:`~vaultspec_core.vaultcore.checks._base.VaultSnapshot`
        from the graph's parsed node data.

        Each node's frontmatter tags, date, and related links are packed into a
        :class:`~vaultspec_core.vaultcore.models.DocumentMetadata`, paired with
        the node's body text, and keyed by filesystem path.

        Returns:
            Dict mapping each document's path to its ``(metadata, body)``
            tuple.
        """

        snapshot: VaultSnapshot = {}
        for node in self.nodes.values():
            if node.phantom or node.path is None:
                continue
            raw_related = node.frontmatter.get("related", [])
            if not isinstance(raw_related, list):
                raw_related = []
            related = [str(r) for r in raw_related if isinstance(r, str)]
            metadata = DocumentMetadata(
                tags=sorted(node.tags),
                date=node.date,
                related=related,
            )
            snapshot[node.path] = (metadata, node.body)
        return snapshot

    def neighbors(
        self,
        name: str,
        direction: str = "out",
    ) -> list[str]:
        """Return neighbor node names for *name*.

        Args:
            name: Document stem.
            direction: ``"out"`` for successors, ``"in"`` for
                predecessors, ``"both"`` for the union.

        Returns:
            Sorted list of neighbor names.
        """
        if name not in self._digraph:
            return []
        if direction == "in":
            return sorted(self._digraph.predecessors(name))
        if direction == "both":
            preds = set(self._digraph.predecessors(name))
            succs = set(self._digraph.successors(name))
            return sorted(preds | succs)
        return sorted(self._digraph.successors(name))

    # -- Metrics (networkx algorithms) ---------------------------------------

    def metrics(
        self,
        feature: str | None = None,
    ) -> GraphMetrics:
        """Compute aggregate statistics via networkx algorithms.

        Delegates to ``nx.density``, ``nx.in_degree_centrality``,
        ``nx.betweenness_centrality``, and
        ``nx.number_weakly_connected_components`` instead of manual
        computation.

        Args:
            feature: Compute metrics only for this feature's subgraph.

        Returns:
            A :class:`GraphMetrics` instance.
        """
        g = self.subgraph(feature=feature)
        nodes = (
            {n.name: n for n in self.get_feature_nodes(feature)}
            if feature
            else self.nodes
        )

        n_nodes = g.number_of_nodes()
        n_edges = g.number_of_edges()

        # --- networkx degree analysis (exclude phantoms) ---
        max_in: tuple[str, int] = ("", 0)
        max_out: tuple[str, int] = ("", 0)
        if n_nodes:
            in_degs = {
                k: v
                for k, v in g.in_degree()
                if k not in self.nodes or not self.nodes[k].phantom
            }
            out_degs = {
                k: v
                for k, v in g.out_degree()
                if k not in self.nodes or not self.nodes[k].phantom
            }
            if in_degs:
                top = max(in_degs, key=lambda k: in_degs[k])
                max_in = (top, in_degs[top])
            if out_degs:
                top = max(out_degs, key=lambda k: out_degs[k])
                max_out = (top, out_degs[top])

        # --- networkx centrality algorithms ---
        in_cent: dict[str, float] = {}
        btwn_cent: dict[str, float] = {}
        if n_nodes > 1:
            in_cent = _top_n(nx.in_degree_centrality(g))
            btwn_cent = _top_n(nx.betweenness_centrality(g))

        # --- feature / type counts (excludes phantoms) ---
        features: set[str] = set()
        by_type: dict[str, int] = {}
        by_feature: dict[str, int] = {}
        total_words = 0
        phantom_count = 0
        for node in nodes.values():
            if node.phantom:
                phantom_count += 1
                continue
            if node.feature:
                features.add(node.feature)
                by_feature[node.feature] = by_feature.get(node.feature, 0) + 1
            dt_key = node.doc_type.value if node.doc_type else "unknown"
            by_type[dt_key] = by_type.get(dt_key, 0) + 1
            total_words += node.word_count

        # --- networkx orphan / dangling ---
        orphan_count = len(self.get_orphaned())
        invalid_count = sum(
            1
            for src, tgt in self._dangling_links
            if src in nodes and tgt in self.nodes and self.nodes[tgt].phantom
        )

        # --- networkx connected components ---
        try:
            components = nx.number_weakly_connected_components(g)
        except nx.NetworkXError:
            components = 0

        return GraphMetrics(
            total_nodes=n_nodes - phantom_count,
            total_edges=n_edges,
            total_features=len(features),
            total_words=total_words,
            density=nx.density(g),
            avg_in_degree=(n_edges / n_nodes if n_nodes else 0.0),
            avg_out_degree=(n_edges / n_nodes if n_nodes else 0.0),
            max_in_degree=max_in,
            max_out_degree=max_out,
            in_degree_centrality=in_cent,
            betweenness_centrality=btwn_cent,
            phantom_count=phantom_count,
            orphan_count=orphan_count,
            dangling_link_count=invalid_count,
            connected_components=components,
            nodes_by_type=dict(sorted(by_type.items())),
            nodes_by_feature=dict(sorted(by_feature.items())),
        )

    # -- ASCII graph rendering (phart) ---------------------------------------

    def render_ascii(
        self,
        feature: str | None = None,
    ) -> str:
        """Render the graph as an ASCII diagram via ``phart``.

        Uses ``phart.ASCIIRenderer`` to produce a native directed-graph
        layout with box-drawn nodes and edge arrows  - the actual graph
        topology, not a hierarchical tree.

        Args:
            feature: When set, render only that feature's subgraph.

        Returns:
            Multi-line ASCII string of the graph layout.
        """
        from phart import ASCIIRenderer

        g = self.subgraph(feature=feature)
        renderer = ASCIIRenderer(g)
        return renderer.render()

    # -- Hierarchical tree rendering (Rich) ----------------------------------

    def render_tree(
        self,
        feature: str | None = None,
    ) -> Tree:
        """Build a Rich :class:`~rich.tree.Tree` for terminal display.

        Renders the vault as a hierarchical tree grouped by feature and
        doc-type.  This is complementary to :meth:`render_ascii` which
        shows the actual graph topology.

        Args:
            feature: Optional feature name to scope the tree.

        Returns:
            A ``rich.tree.Tree`` ready for ``console.print()``.
        """
        from rich.tree import Tree as RichTree

        if feature:
            return self._render_feature_tree(feature)

        m = self.metrics()
        root = RichTree(
            f"[bold].vault[/bold]  "
            f"[dim]{m.total_nodes} docs, "
            f"{m.total_edges} links, "
            f"{m.total_features} features[/dim]"
        )

        for feat in self.get_features():
            feat_nodes = self.get_feature_nodes(feat)
            feat_branch = root.add(
                f"[bold cyan]#{feat}[/bold cyan]  [dim]{len(feat_nodes)} docs[/dim]"
            )
            self._add_typed_nodes(feat_branch, feat_nodes)

        untagged = [n for n in self.nodes.values() if not n.feature and not n.phantom]
        if untagged:
            branch = root.add(
                "[bold yellow](untagged)[/bold yellow]"
                f"  [dim]{len(untagged)} docs[/dim]"
            )
            self._add_typed_nodes(
                branch,
                sorted(untagged, key=lambda n: n.name),
            )

        return root

    def _render_feature_tree(self, feature: str) -> Tree:
        """Render a tree scoped to a single feature."""
        from rich.tree import Tree as RichTree

        nodes = self.get_feature_nodes(feature)
        m = self.metrics(feature=feature)

        root = RichTree(
            f"[bold cyan]#{feature}[/bold cyan]  "
            f"[dim]{m.total_nodes} docs, "
            f"{m.total_edges} links[/dim]"
        )
        self._add_typed_nodes(root, nodes)
        return root

    def _add_typed_nodes(
        self,
        parent: Tree,
        nodes: list[DocNode],
    ) -> None:
        """Group *nodes* by doc_type under *parent*."""
        by_type: dict[str, list[DocNode]] = {}
        for node in nodes:
            key = node.doc_type.value if node.doc_type else "unknown"
            by_type.setdefault(key, []).append(node)

        for type_name in sorted(by_type):
            type_nodes = by_type[type_name]
            type_branch = parent.add(
                f"[bold]{type_name}[/bold]  [dim]({len(type_nodes)})[/dim]"
            )
            for node in type_nodes:
                label = self._node_label(node)
                node_branch = type_branch.add(label)

                for target in sorted(node.out_links):
                    target_node = self.nodes.get(target)
                    if target_node and target_node.phantom:
                        node_branch.add(
                            f"[dim]-> {target}[/dim]  "
                            f"[yellow italic](not created)[/yellow italic]"
                        )
                    elif target_node:
                        dt_val = (
                            target_node.doc_type.value if target_node.doc_type else "?"
                        )
                        node_branch.add(
                            f"[dim]-> {target}[/dim]  [dim italic]{dt_val}[/dim italic]"
                        )
                    else:
                        node_branch.add(f"[red dim]-> {target} (dangling)[/red dim]")

    @staticmethod
    def _node_label(node: DocNode) -> str:
        """Format a single-line Rich label for a node."""
        parts = [f"[bold]{node.name}[/bold]"]
        if node.title:
            parts.append(f"[italic]{node.title}[/italic]")
        if node.date:
            parts.append(f"[dim]{node.date}[/dim]")
        meta = []
        if node.word_count:
            meta.append(f"{node.word_count}w")
        meta.append(f"{len(node.in_links)}in")
        meta.append(f"{len(node.out_links)}out")
        parts.append(f"[dim]({', '.join(meta)})[/dim]")
        return "  ".join(parts)

    # -- JSON serialisation (networkx node_link_data) ------------------------

    def to_dict(
        self,
        feature: str | None = None,
        include_body: bool = False,
    ) -> dict[str, Any]:
        """Return the graph as a JSON-serialisable dictionary.

        Uses ``networkx.readwrite.json_graph.node_link_data`` for the
        core node/edge structure, enriched with vault-specific metrics.

        Args:
            feature: When set, export only that feature's subgraph.
            include_body: Include the full markdown body text in each
                node.  Defaults to ``False`` to keep output compact.

        Returns:
            Dictionary with ``directed``, ``multigraph``, ``graph``,
            ``nodes``, ``edges``, and ``metrics`` keys.
        """
        g = self.subgraph(feature=feature)

        # networkx native serialisation
        data = json_graph.node_link_data(g)

        # Strip body from nodes unless requested
        if not include_body:
            for node_dict in data.get("nodes", []):
                node_dict.pop("body", None)

        # Inject body when requested (body is not on the nx node)
        if include_body:
            for node_dict in data.get("nodes", []):
                nid = node_dict.get("id", "")
                doc = self.nodes.get(nid)
                if doc:
                    node_dict["body"] = doc.body

        # Enrich with vault-specific metadata
        m = self.metrics(feature=feature)
        data["root"] = str(self.root_dir)
        data["feature"] = feature
        data["metrics"] = m.to_dict()

        return data

    def to_json(
        self,
        feature: str | None = None,
        include_body: bool = False,
        indent: int = 2,
    ) -> str:
        """Serialise the graph to a JSON string.

        Args:
            feature: Scope to a single feature.
            include_body: Include full markdown body in output.
            indent: JSON indentation level.

        Returns:
            JSON string.
        """
        return json.dumps(
            self.to_dict(
                feature=feature,
                include_body=include_body,
            ),
            indent=indent,
            default=str,
        )

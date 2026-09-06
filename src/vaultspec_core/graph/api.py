"""Build, query, and render the vault document relationship graph.

Turns ``vaultcore`` scanning, metadata parsing, and wiki-link extraction into
a queryable directed graph of ``.vault/`` documents backed by
``networkx.DiGraph``. Delegates rendering to ``phart`` (ASCII topology) and
:func:`~vaultspec_core.cli.rendering.render_tree` (box-free hierarchical tree),
and serialisation to ``networkx.readwrite.json_graph``.

Example::

    graph = VaultGraph(root_dir)
    lines = graph.render_tree_lines(feature="my-feature")  # list[TreeLine]
    ascii = graph.render_ascii(feature="my-feature")       # phart ASCII
    data  = graph.to_dict(feature="my-feature")            # JSON-ready dict
    stats = graph.metrics()                                # GraphMetrics

Exports:
    :class:`DocNode`: Node carrying full frontmatter, body, and link metadata.
    :class:`GraphMetrics`: Computed shape and size statistics for the graph.
    :class:`VaultGraph`: Main entry point; instantiate with a vault root dir.
"""

from __future__ import annotations

import logging
from collections import Counter
from typing import TYPE_CHECKING, Any, cast

import networkx as nx

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
from . import api_export, rendering
from .algorithms import (
    PAGERANK_ALPHA,
    betweenness_centrality,
    docnode_from_attrs,
    edge_kind,
    extract_feature,
    extract_title,
    pagerank,
    top_n,
)
from .models import DocNode, EncodingIssue, GraphCounts, GraphMetrics
from .networkx_runtime import (
    NetworkXGraph,
    directed_graph,
    ego_graph,
    node_link_data,
    node_link_graph,
)
from .networkx_runtime import density as graph_density

if TYPE_CHECKING:
    import pathlib

    from vaultspec_core.cli.rendering import TreeLine

    from ..vaultcore.checks._base import VaultSnapshot
    from . import cache

logger = logging.getLogger(__name__)


__all__ = ["DocNode", "GraphMetrics", "VaultGraph"]

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

    Every explicit edge carries three attributes set during build:

    - ``kind``: provenance of the reference, one of ``"body"`` (a body
      wiki-link only), ``"related"`` (a ``related:`` frontmatter entry
      only), or ``"both"`` (the target is reached by both sources).
    - ``multiplicity``: the total number of times the source references
      the target, summing body citations and ``related:`` entries.
    - ``weight``: ``multiplicity`` normalised against the maximum
      multiplicity of any edge in the graph, so the strongest edge has
      weight ``1.0``.  Derived/implicit relatedness never enters these
      edges; it is computed separately in
      :mod:`vaultspec_core.graph.derived`.

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

    def __init__(self, root_dir: pathlib.Path, *, use_cache: bool = True) -> None:
        self.root_dir = root_dir
        #: The git ref this graph was built from, or ``None`` for a
        #: working-tree build. Set only via :meth:`from_ref`.
        self.ref: str | None = None
        self.nodes: dict[str, DocNode] = {}
        self._digraph: NetworkXGraph = directed_graph()
        self._dangling_links: list[tuple[str, str]] = []
        self._stem_index: dict[str, list[str]] = {}
        self._raw_texts: dict[pathlib.Path, tuple[str, bool]] = {}
        self._encoding_issues: list[EncodingIssue] = []
        self._build_graph(use_cache=use_cache)

    @classmethod
    def from_ref(cls, root_dir: pathlib.Path, ref: str) -> VaultGraph:
        """Build a graph from the vault corpus at a git *ref*, without a checkout.

        Reads the vault documents from the git object database at *ref* (issue
        #160) instead of the working tree. The build runs with the graph cache
        disabled and the working-tree migration pass skipped - a read-only view
        of history must neither be served stale working-tree data nor write
        working-tree state (the ``ref-scoped-reads-bypass-worktree-cache``
        rule). Document-type classification reads each blob's tree path rather
        than a filesystem location, so the resulting graph is structurally
        identical to a working-tree build of the same corpus.

        Args:
            root_dir: Repository working directory (used for ``git -C`` and as
                the envelope ``root``).
            ref: A branch name, tag, or commit-ish to read the corpus from.

        Returns:
            A :class:`VaultGraph` over the corpus as it stood at *ref*.

        Raises:
            RefScanError: When *root_dir* is not a git repository or *ref*
                does not resolve to a commit.
        """
        import pathlib

        from ..config import get_config
        from .refscan import read_vault_at_ref

        graph = cls.__new__(cls)
        graph.root_dir = root_dir
        graph.ref = ref
        graph.nodes = {}
        graph._digraph = nx.DiGraph()
        graph._dangling_links = []
        graph._stem_index = {}
        graph._raw_texts = {}
        graph._encoding_issues = []

        docs_dir_name = pathlib.Path(get_config().docs_dir).name
        corpus = read_vault_at_ref(root_dir, ref, docs_dir_name)
        graph._rebuild_from_corpus(corpus, docs_dir_name)
        return graph

    # -- Construction --------------------------------------------------------

    def _build_graph(self, *, use_cache: bool = True) -> None:
        """Populate the graph, loading from the fingerprint cache when valid.

        Scans the vault once into a file list.  When *use_cache* is set and a
        cache file exists whose manifest passes the racily-clean validation
        (same file set, same per-file size and mtime, and a matching content
        hash for any file whose mtime is not older than the cache file's own
        mtime), the serialised canonical graph is loaded and the full parse is
        skipped.  On any divergence - a changed, added, or removed file, an
        absent cache, or a corrupt cache - the graph is rebuilt from the
        scanned files and the cache (manifest hashes included) is rewritten.

        Validation is stat-first: full content hashing happens only on the
        save path after a rebuild, never on the warm read, so the cache's own
        upkeep stays cheap relative to the parse it avoids.  A corrupt cache
        degrades silently to a full rebuild rather than crashing or serving
        stale data.

        Args:
            use_cache: When ``True`` (default), attempt a cache load before
                rebuilding and rewrite the cache after a rebuild.  When
                ``False``, ignore and do not write the cache (a forced fresh
                build).
        """
        from . import cache as cache_mod

        logger.info("Building vault graph from %s", self.root_dir)

        scanned_files = list(scan_vault(self.root_dir))
        path = cache_mod.cache_path(self.root_dir)

        if use_cache:
            payload = cache_mod.load(path)
            if payload is not None:
                try:
                    cache_mtime_ns: int | None = path.stat().st_mtime_ns
                except OSError:
                    cache_mtime_ns = None
                if cache_mod.validate(
                    payload.manifest,
                    scanned_files,
                    self.root_dir,
                    cache_mtime_ns=cache_mtime_ns,
                ):
                    logger.info("Graph cache hit at %s; skipping re-parse", path)
                    self._load_from_cache(payload)
                    return
            logger.info("Graph cache miss at %s; rebuilding", path)

        self._rebuild_from_files(scanned_files)

        if use_cache:
            cache_mod.save(
                path,
                cache_mod.fingerprint_vault(scanned_files, self.root_dir),
                self._to_cache_graph(),
                self._dangling_links,
                [
                    (str(issue.path), issue.kind, issue.detail, issue.start)
                    for issue in self._encoding_issues
                ],
            )

    def _to_cache_graph(self) -> dict[str, Any]:
        """Return the node-link serialisation of the canonical graph for caching.

        Uses the same ``edges="edges"`` node-link contract the JSON export
        uses, then injects each node's body text (which is held on the
        :class:`DocNode`, not on the networkx node) so a cache load can
        reconstruct a behaviourally identical graph, including
        :meth:`to_dict` with ``include_body=True``.

        Returns:
            A node-link ``dict`` with body text attached to each node.
        """
        data = node_link_data(self._digraph)
        for node_dict in data.get("nodes", []):
            nid = node_dict.get("id", "")
            doc = self.nodes.get(nid)
            node_dict["body"] = doc.body if doc is not None else ""
        return data

    def _load_from_cache(self, payload: cache.GraphCachePayload) -> None:
        """Reconstruct the graph state from a validated cache payload.

        Rebuilds ``self._digraph``, ``self.nodes``, ``self._stem_index``, and
        ``self._dangling_links`` from the serialised node-link data so the
        loaded graph is behaviourally identical to a fresh build (same nodes,
        edges, attributes, and node-size metrics).  No filesystem parsing
        occurs.

        Args:
            payload: A cache payload that has already passed
                :func:`vaultspec_core.graph.cache.validate`.
        """
        self._digraph = node_link_graph(payload.graph)
        self.nodes = {}
        self._stem_index = {}
        by_stem: dict[str, list[str]] = {}
        for key in self._digraph.nodes():
            attrs = self._digraph.nodes[key]
            self.nodes[key] = docnode_from_attrs(key, attrs)
            # The node body is held on the DocNode, not the nx node; pull it
            # back off the cached node attrs and drop it so the nx node
            # attribute set matches a fresh build exactly.
            body = attrs.pop("body", "")
            self.nodes[key].body = body
            # Phantoms are excluded from _stem_index to match fresh-build
            # semantics: _rebuild_from_files only indexes real (non-phantom)
            # nodes in passes 1a/1b; phantoms are added later in pass 2 and
            # never entered into _stem_index.
            if not attrs.get("phantom", False):
                bare_stem = key.split("/", 1)[1] if "/" in key else key
                by_stem.setdefault(bare_stem, []).append(key)
        for bare_stem, keys in by_stem.items():
            self._stem_index[bare_stem] = sorted(keys)
        self._dangling_links = [(pair[0], pair[1]) for pair in payload.dangling_links]
        # A document that failed to read or decode never becomes a usable node,
        # so the cache carries these separately; restoring them keeps a warm
        # run's encoding findings identical to a cold one's.
        from pathlib import Path as _Path

        self._encoding_issues = [
            EncodingIssue(_Path(raw_path), kind, detail, start)
            for raw_path, kind, detail, start in payload.encoding_issues
        ]
        logger.info(
            "Graph loaded from cache: %d nodes, %d edges",
            self._digraph.number_of_nodes(),
            self._digraph.number_of_edges(),
        )

    def _rebuild_from_files(self, scanned_files: list[pathlib.Path]) -> None:
        """Rebuild the graph by parsing every scanned file.

        Uses a two-pass strategy:

        1. **Pass 1**  - create :class:`DocNode` instances, detecting stem
           collisions.  When two files share the same stem (e.g.
           ``adr/my-doc.md`` and ``reference/my-doc.md``), all colliding
           nodes are re-keyed as ``type/stem`` so that no data is silently
           dropped.
        2. **Pass 2**  - extract links and create directed edges.  Bare
           wiki-link stems that match multiple qualified keys fan-out to
           all variants (with a logged warning).

        Args:
            scanned_files: The vault document paths to parse, as returned by
                ``scan_vault``.
        """
        self.nodes = {}
        self._digraph = nx.DiGraph()
        self._dangling_links = []
        self._raw_texts = {}
        self._encoding_issues = []

        # Pass 1a: collect all DocNodes keyed by stem, detecting collisions
        by_stem: dict[str, list[DocNode]] = {}

        for path in scanned_files:
            logger.debug("Graph pass 1: reading %s", path)
            stem = path.stem
            doc_type = get_doc_type(path, self.root_dir)

            node = DocNode(path=path, name=stem, doc_type=doc_type)

            content = self._ingest_document(path)
            if content is not None:
                self._populate_node_from_content(node, content)

            by_stem.setdefault(stem, []).append(node)

        self._assemble_from_by_stem(by_stem)

    def _ingest_document(self, path: pathlib.Path) -> str | None:
        """Read *path* once, recording its raw text and any encoding issue.

        The single ingress read: the file's bytes are read exactly once,
        decoded as UTF-8, and newline-normalised the way ``read_text``'s
        universal-newline mode would (``\\r\\n`` and ``\\r`` become ``\\n``)
        so the parse consumes identical input to the previous per-consumer
        reads.  The normalised text and the source's CRLF convention are
        retained in :attr:`raw_texts` for content-consuming checks, and a
        read or decode failure is recorded in :attr:`encoding_issues`
        instead of being silently dropped.

        Returns:
            The normalised document text, or ``None`` when the file could
            not be read or decoded.
        """
        try:
            raw_bytes = path.read_bytes()
        except OSError as e:
            self._encoding_issues.append(EncodingIssue(path, "read", str(e), None))
            logger.warning("Failed to read metadata from %s: %s", path, e)
            return None
        try:
            decoded = raw_bytes.decode("utf-8")
        except UnicodeDecodeError as e:
            self._encoding_issues.append(
                EncodingIssue(path, "decode", e.reason, e.start)
            )
            logger.warning("Failed to read metadata from %s: %s", path, e)
            return None
        crlf = "\r\n" in decoded
        content = decoded.replace("\r\n", "\n").replace("\r", "\n")
        self._raw_texts[path] = (content, crlf)
        return content

    def ensure_raw_texts(self) -> None:
        """Guarantee :attr:`raw_texts` is populated for a working-tree graph.

        A cold build fills the raw-text map during its parse; a cache-hit
        build parses nothing, so a caller that needs document text (the
        check pipeline) invokes this to perform the run's single ingress
        read pass.  A no-op when the map is already populated or when the
        graph is ref-scoped (checks do not run against history).
        """
        if self._raw_texts or self.ref is not None:
            return
        from ..vaultcore.scanner import scan_vault

        self._encoding_issues = []
        for path in scan_vault(self.root_dir):
            self._ingest_document(path)

    @property
    def raw_texts(self) -> dict[pathlib.Path, tuple[str, bool]]:
        """Per-document ``(normalised text, source_had_crlf)`` in scan order.

        Populated by a cold build or :meth:`ensure_raw_texts`; empty after a
        bare cache hit or for a ref-scoped graph.
        """
        return self._raw_texts

    @property
    def encoding_issues(self) -> list[EncodingIssue]:
        """Read and decode failures observed during the ingress read."""
        return self._encoding_issues

    def _rebuild_from_corpus(
        self, corpus: list[tuple[str, str]], docs_dir_name: str
    ) -> None:
        """Rebuild the graph from in-memory ``(tree_path, content)`` pairs.

        The ref-scoped build path (issue #160): instead of walking the working
        tree, the corpus is read from the git object database by
        :func:`vaultspec_core.graph.refscan.read_vault_at_ref`. Each pair
        carries a virtual tree path (e.g. ``.vault/adr/foo.md``) and the blob's
        UTF-8 text. Document-type classification reads the tree path via
        :func:`vaultspec_core.vaultcore.scanner.get_doc_type_from_tree_path`,
        and the node ``path`` is the virtual tree path. After Pass 1a the build
        is identical to the working-tree path, so the graph is structurally the
        same as a checkout-based build of the same corpus.

        Args:
            corpus: ``(tree_path, content)`` pairs for the ref's vault docs.
            docs_dir_name: The configured docs directory name (e.g. ``.vault``).
        """
        import pathlib

        from ..vaultcore.scanner import get_doc_type_from_tree_path

        self.nodes = {}
        self._digraph = nx.DiGraph()
        self._dangling_links = []

        by_stem: dict[str, list[DocNode]] = {}
        for tree_path, content in corpus:
            stem = pathlib.PurePosixPath(tree_path).stem
            doc_type = get_doc_type_from_tree_path(tree_path, docs_dir_name)
            node = DocNode(path=None, name=stem, doc_type=doc_type, tree_path=tree_path)
            try:
                self._populate_node_from_content(node, content)
            except (ValueError, KeyError) as e:
                logger.warning("Failed to parse blob %s: %s", tree_path, e)
            by_stem.setdefault(stem, []).append(node)

        self._assemble_from_by_stem(by_stem)

    @staticmethod
    def _populate_node_from_content(node: DocNode, content: str) -> None:
        """Parse a document's *content* and populate *node*'s metadata fields.

        Shared by the working-tree and ref-scoped build paths so both derive
        tags, dates, feature, frontmatter, body, word count, and title from
        the same content-bound parsers (which never touch the filesystem).
        """
        metadata, body = parse_vault_metadata(content)
        raw_fm, _ = parse_frontmatter(content)

        node.tags = set(metadata.tags)
        node.date = metadata.date
        node.modified = metadata.modified
        node.feature = extract_feature(node.tags)
        node.frontmatter = raw_fm
        node.body = body
        node.word_count = len(body.split())
        node.title = extract_title(body)

    def _assemble_from_by_stem(self, by_stem: dict[str, list[DocNode]]) -> None:
        """Run the shared graph-assembly passes over the collected nodes.

        Passes 1b through 4 (key assignment / collision qualification, edge
        extraction, in/out-link sync, and node-size hints) are identical for
        the working-tree and ref-scoped build paths, which differ only in how
        Pass 1a's ``by_stem`` map is produced.

        Args:
            by_stem: Map of bare stem to the :class:`DocNode` instances that
                share it, as produced by the Pass-1a collectors.
        """
        # Pass 1b: assign unique keys  - qualify colliding stems with
        # their doc-type prefix, build a stem-to-keys index for link
        # resolution in pass 2.
        self._stem_index = {}

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
                # Sort so the index is deterministic across platforms and
                # matches the cache-rebuild path (which also sorts); raw scan
                # order is filesystem-dependent and diverges on Linux vs
                # Windows, breaking cached-vs-fresh parity.
                self._stem_index[stem] = sorted(keys)
                logger.warning(
                    "Stem collision for '%s': qualified as %s",
                    stem,
                    sorted(keys),
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
                # Keep the body and related extractions separate so each
                # resolved edge can record its provenance (body wiki-link,
                # related frontmatter, or both).  Both extractors now return
                # a Counter, preserving per-target multiplicity.
                body_links = extract_wiki_links(node.body)
                related_links = extract_related_links(
                    node.frontmatter.get("related", []),
                )

                # Resolve each raw target to one or more node keys, summing
                # the source multiplicity onto every resolved key and unioning
                # the provenance kinds.  Iterating a Counter yields its keys.
                target_counts: Counter[str] = Counter()
                target_kinds: dict[str, set[str]] = {}
                for raw_target, count in body_links.items():
                    for resolved_key in self._resolve_link(raw_target):
                        target_counts[resolved_key] += count
                        target_kinds.setdefault(resolved_key, set()).add("body")
                for raw_target, count in related_links.items():
                    for resolved_key in self._resolve_link(raw_target):
                        target_counts[resolved_key] += count
                        target_kinds.setdefault(resolved_key, set()).add("related")

                node.out_links = set(target_counts)

                for target_key, multiplicity in target_counts.items():
                    kind = edge_kind(target_kinds[target_key])
                    if target_key in self.nodes:
                        self.nodes[target_key].in_links.add(name)
                        self._digraph.add_edge(
                            name,
                            target_key,
                            kind=kind,
                            multiplicity=multiplicity,
                        )
                        if self.nodes[target_key].phantom and not self._is_archived(
                            target_key
                        ):
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
                        self._digraph.add_edge(
                            name,
                            target_key,
                            kind=kind,
                            multiplicity=multiplicity,
                        )
                        if not self._is_archived(target_key):
                            self._dangling_links.append(
                                (name, target_key),
                            )
            except (OSError, UnicodeDecodeError) as e:
                logger.warning(
                    "Failed to extract links from %s: %s",
                    node.path,
                    e,
                )

        # Pass 2b: normalise edge weight against the maximum multiplicity in
        # the graph so the strongest explicit edge has weight 1.0 and every
        # other edge is its multiplicity as a fraction of that maximum.  The
        # scheme is linear, deterministic, and exactly testable:
        #   weight = multiplicity / max_multiplicity_in_graph
        # When the graph has no edges there is nothing to normalise.
        multiplicities = [
            data["multiplicity"] for _, _, data in self._digraph.edges(data=True)
        ]
        max_multiplicity = max(multiplicities) if multiplicities else 0
        for _src, _tgt, data in self._digraph.edges(data=True):
            data["weight"] = (
                data["multiplicity"] / max_multiplicity if max_multiplicity else 0.0
            )

        # Pass 3: sync nx node attrs with updated in_links/out_links
        for name, node in self.nodes.items():
            self._digraph.nodes[name]["out_links"] = sorted(
                node.out_links,
            )
            self._digraph.nodes[name]["in_links"] = sorted(
                node.in_links,
            )

        # Pass 4: node-size hints.  Attach pagerank and raw in-degree so a GUI
        # consumer can size nodes without recomputing.  PageRank uses the
        # pure-Python power iteration in pagerank with a fixed damping factor
        # (PAGERANK_ALPHA) and a uniform initial vector, so the result is
        # deterministic for a fixed graph and exactly testable.  An empty
        # graph yields no scores.
        if self._digraph.number_of_nodes():
            pagerank_scores = pagerank(self._digraph, alpha=PAGERANK_ALPHA)
        else:
            pagerank_scores = {}
        in_degree = dict(self._digraph.in_degree())
        for name in self._digraph.nodes():
            self._digraph.nodes[name]["pagerank"] = pagerank_scores.get(name, 0.0)
            self._digraph.nodes[name]["in_degree"] = in_degree.get(name, 0)

        logger.info(
            "Graph build complete: %d nodes, %d edges",
            self._digraph.number_of_nodes(),
            self._digraph.number_of_edges(),
        )

    def _is_archived(self, target: str) -> bool:
        """Check if target exists under .vault/_archive/."""
        from ..config import get_config

        cfg = get_config()
        archive_dir = self.root_dir / cfg.docs_dir / "_archive"
        if not archive_dir.exists():
            return False
        target_norm = target.replace("\\", "/")
        if "/" in target_norm:
            return (archive_dir / f"{target_norm}.md").exists()
        else:
            return len(list(archive_dir.rglob(f"{target_norm}.md"))) > 0

    def _resolve_link(self, target: str) -> list[str]:
        """Resolve a wiki-link target to one or more node keys.

        Resolution order:

        1. Exact match against an existing node key (handles both bare
           stems and already-qualified ``type/stem`` references).
        2. Stem index lookup  - if the bare stem maps to multiple
           qualified keys, all are returned and a warning is logged.
        3. Match in .vault/_archive/ - returns the resolved archived key
           so it can be resolved without being flagged as dangling.
        4. No match  - returns the original target so it is recorded as
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

        # Try to resolve against .vault/_archive/
        from ..config import get_config

        cfg = get_config()
        archive_dir = self.root_dir / cfg.docs_dir / "_archive"
        if archive_dir.exists():
            target_norm = target.replace("\\", "/")
            if "/" in target_norm:
                if (archive_dir / f"{target_norm}.md").exists():
                    return [target_norm]
            else:
                matches = list(archive_dir.rglob(f"{target_norm}.md"))
                if matches:
                    resolved: list[str] = []
                    for match in matches:
                        rel = match.relative_to(archive_dir)
                        key = str(rel.with_suffix("")).replace("\\", "/")
                        resolved.append(key)
                    return resolved

        # No match  - treat as dangling link
        return [target]

    # -- Direct networkx access ----------------------------------------------

    @property
    def digraph(self) -> NetworkXGraph:
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
    ) -> NetworkXGraph:
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

    def ego_subgraph(
        self,
        node: str,
        depth: int = 1,
    ) -> NetworkXGraph:
        """Return the local (ego) subgraph around *node* up to *depth* hops.

        Mirrors Obsidian's local-graph view: the centre document plus every
        document reachable within *depth* link hops in either direction.  The
        traversal is undirected (a backlink is as relevant as a forward link
        for local context) via ``nx.ego_graph(..., undirected=True)``, but the
        returned graph is the directed subgraph induced on those nodes, so
        edge direction and the ``kind``/``multiplicity``/``weight`` attributes
        are preserved.

        Args:
            node: Centre node key.  Must exist in the graph.
            depth: Radius in hops (``>= 0``).  ``0`` returns just the centre
                node; ``1`` adds its immediate neighbours, and so on.

        Returns:
            A directed subgraph view of the canonical graph scoped to the ego
            neighbourhood.

        Raises:
            KeyError: If *node* is not a key in the graph.
            ValueError: If *depth* is negative.
        """
        if node not in self._digraph:
            raise KeyError(node)
        if depth < 0:
            raise ValueError(f"depth must be >= 0, got {depth}")
        ego = ego_graph(
            self._digraph,
            node,
            radius=depth,
            undirected=True,
        )
        # Induce the directed subgraph on the ego node set so edge direction
        # and edge attributes survive.
        return self._digraph.subgraph(ego.nodes())

    # -- Query methods -------------------------------------------------------

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

        Each node's frontmatter tags, date, modified stamp, and related
        links are packed into a
        :class:`~vaultspec_core.vaultcore.models.DocumentMetadata`, paired with
        the node's body text, and keyed by filesystem path.

        Returns:
            Dict mapping each document's path to its ``(metadata, body)``
            tuple.
        """

        snapshot: VaultSnapshot = {}
        for node in self.nodes.values():
            # A working-tree snapshot is keyed by concrete filesystem paths.
            # Phantoms and ref-scoped nodes (which carry a virtual tree_path,
            # not a filesystem path) have ``path is None`` and are excluded so
            # the snapshot only ever describes real on-disk documents.
            if node.phantom or node.path is None:
                continue
            raw_related = node.frontmatter.get("related", [])
            related: list[str] = []
            if isinstance(raw_related, list):
                related_items = cast("list[Any]", raw_related)
                related = [str(r) for r in related_items if isinstance(r, str)]
            raw_superseded_by = node.frontmatter.get("superseded_by")
            superseded_by = (
                raw_superseded_by if isinstance(raw_superseded_by, str) else None
            )
            raw_step_id = node.frontmatter.get("step_id")
            step_id = raw_step_id if isinstance(raw_step_id, str) else None
            raw_body_schema = node.frontmatter.get("body_schema")
            body_schema = raw_body_schema if isinstance(raw_body_schema, str) else None
            raw_body_hash = node.frontmatter.get("body_hash")
            body_hash = raw_body_hash if isinstance(raw_body_hash, str) else None
            metadata = DocumentMetadata(
                tags=sorted(node.tags),
                date=node.date,
                modified=node.modified,
                related=related,
                superseded_by=superseded_by,
                step_id=step_id,
                body_schema=body_schema,
                body_hash=body_hash,
            )
            snapshot[node.path] = (metadata, node.body)
        return snapshot

    # -- Metrics (networkx algorithms) ---------------------------------------

    def counts(self, feature: str | None = None) -> GraphCounts:
        """Return the cheap descriptive counts for the graph or a feature.

        Produces exactly the ``total_nodes``, ``total_edges``, and
        ``total_features`` values :meth:`metrics` reports, without running
        any of the graph-theoretic analysis (centrality, components,
        density) that method bundles.  This is the surface render and
        orientation paths use; :meth:`metrics` is the explicit opt-in for
        analysis.

        Args:
            feature: When set, count only this feature's subgraph.

        Returns:
            A :class:`GraphCounts` instance.
        """
        if feature:
            g = self.subgraph(feature=feature)
            nodes: dict[str, DocNode] = {
                n.name: n for n in self.get_feature_nodes(feature)
            }
        else:
            g = self._digraph
            nodes = self.nodes
        phantom_count = 0
        features: set[str] = set()
        for node in nodes.values():
            if node.phantom:
                phantom_count += 1
            elif node.feature:
                features.add(node.feature)
        return GraphCounts(
            docs=g.number_of_nodes() - phantom_count,
            links=g.number_of_edges(),
            features=len(features),
        )

    def metrics(
        self,
        feature: str | None = None,
        *,
        _g: NetworkXGraph | None = None,
    ) -> GraphMetrics:
        """Compute aggregate statistics via graph-library algorithms.

        Delegates to ``nx.density``, ``nx.in_degree_centrality``,
        ``nx.number_weakly_connected_components``, and betweenness
        centrality through the C-backed engine seam
        (:func:`betweenness_centrality`, ``rustworkx`` with a networkx
        fallback) instead of manual computation.

        Args:
            feature: Compute metrics only for this feature's subgraph.
            _g: Pre-computed subgraph from :meth:`subgraph`. When
                supplied, the internal :meth:`subgraph` call is skipped
                so callers that already hold a reference (e.g.
                :meth:`to_dict`) avoid a redundant traversal and the
                expensive betweenness computation runs exactly once.
                This parameter is intentionally private (underscore
                prefix) and not part of the public API.

        Returns:
            A :class:`GraphMetrics` instance.
        """
        g = _g if _g is not None else self.subgraph(feature=feature)
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
            in_cent = top_n(nx.in_degree_centrality(g))
            btwn_cent = top_n(betweenness_centrality(g))

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
            density=graph_density(g),
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
        return rendering.render_ascii(self, feature=feature)

    # -- Hierarchical tree rendering (box-free) --------------------------------

    def render_tree_lines(
        self,
        feature: str | None = None,
    ) -> list[TreeLine]:
        """Build a box-free :class:`~vaultspec_core.cli.rendering.TreeLine` list.

        Renders the vault as a hierarchical tree grouped by feature and
        doc-type, using the plain-text shape vocabulary.  This is
        complementary to :meth:`render_ascii` which shows the actual graph
        topology.

        Args:
            feature: Optional feature name to scope the tree.

        Returns:
            A list of :class:`~vaultspec_core.cli.rendering.TreeLine` objects
            ready for :func:`~vaultspec_core.cli.rendering.render_tree`.
        """
        return rendering.render_tree_lines(self, feature=feature)

    #: Maximum lines the tree render prints.  The title always carries the
    #: full corpus counts, the truncation is explicitly marked, and the
    #: ``--json`` envelope remains the uncapped machine contract, per the
    #: report-volume policy.
    TREE_RENDER_CAP = rendering.TREE_RENDER_CAP

    def render_tree(
        self,
        feature: str | None = None,
    ) -> None:
        """Print a box-free hierarchical tree to the console.

        Renders the vault grouped by feature and doc-type via the plain-text
        shape vocabulary.  This is complementary to :meth:`render_ascii` which
        shows the actual graph topology.  At most :attr:`TREE_RENDER_CAP`
        lines are printed; a marked truncation line reports the remainder and
        points at feature scoping or ``--json``.

        Args:
            feature: Optional feature name to scope the tree.
        """
        rendering.render_tree(self, feature=feature)

    # -- JSON serialisation (networkx node_link_data) ------------------------

    def _relativise_node_path(self, raw_path: Any) -> str | None:
        """Return *raw_path* as a vault-relative POSIX path, or ``None``.

        Args:
            raw_path: The ``path`` value off a serialised node dict.

        Returns:
            The vault-relative POSIX path string, or ``None``.
        """
        return api_export.relativise_node_path(self.root_dir, raw_path)

    def to_dict(
        self,
        feature: str | None = None,
        include_body: bool = False,
        *,
        node: str | None = None,
        depth: int = 1,
        include_derived: bool = True,
        derived_limit: int | None = None,
        derived_offset: int = 0,
    ) -> dict[str, Any]:
        """Return the graph as a JSON-serialisable dictionary.

        Uses ``networkx.readwrite.json_graph.node_link_data`` for the
        core node/edge structure, enriched with vault-specific metrics, the
        node-size hints carried on each node (``pagerank``, ``in_degree``),
        the explicit-edge attributes carried on each edge (``kind``,
        ``multiplicity``, ``weight``), and a parallel ``derived_edges`` array
        of implicit relatedness edges that is never mixed into the canonical
        ``edges`` array.

        Scoping precedence: when *node* is given the export is the ego
        subgraph around it at *depth* hops; otherwise *feature* scopes to a
        single feature; otherwise the full graph is exported.

        Args:
            feature: When set (and *node* is unset), export only that
                feature's subgraph.
            include_body: Include the full markdown body text in each
                node.  Defaults to ``False`` to keep output compact.
            node: When set, export the ego subgraph around this node key.
            depth: Ego-graph radius in hops; only used when *node* is set.
            include_derived: When ``True`` (default), emit the
                ``derived_edges`` array; when ``False`` emit an empty one.

        Returns:
            Dictionary with ``directed``, ``multigraph``, ``graph``,
            ``nodes``, ``edges``, ``derived_edges``, ``root``, ``ref``,
            ``feature``, and ``metrics`` keys. ``ref`` names the git ref for a
            ref-scoped build (issue #160) and is ``None`` for a working-tree
            build.
        """
        return api_export.to_dict(
            self,
            feature=feature,
            include_body=include_body,
            node=node,
            depth=depth,
            include_derived=include_derived,
            derived_limit=derived_limit,
            derived_offset=derived_offset,
        )

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
        return api_export.to_json(
            self,
            feature=feature,
            include_body=include_body,
            indent=indent,
        )

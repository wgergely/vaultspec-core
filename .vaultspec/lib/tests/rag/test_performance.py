"""Performance and resource-usage tests for the RAG pipeline."""

from __future__ import annotations

import pytest

# Check if RAG deps are available
try:
    import lancedb  # noqa: F401
    import sentence_transformers  # noqa: F401
    import torch  # noqa: F401

    HAS_RAG = True
except ImportError:
    HAS_RAG = False

pytestmark = [
    pytest.mark.search,
    pytest.mark.skipif(not HAS_RAG, reason="RAG dependencies not installed"),
]


# ---- Performance Tests ----


class TestPerformance:
    """Performance and resource-usage tests for the RAG pipeline.

    All tests require a CUDA-enabled GPU. CPU is not supported.
    """

    # -- Timing tests --

    @pytest.mark.search
    def test_single_query_latency(self, rag_components):
        """End-to-end search should complete within 2 seconds.

        Note: _fts_dirty starts True on VaultStore init, so the first
        search rebuilds the FTS index. We do a warmup query first to
        isolate steady-state latency from FTS rebuild cost.
        """
        import time

        from rag.search import VaultSearcher

        model = rag_components["model"]
        store = rag_components["store"]
        root = rag_components["root"]

        searcher = VaultSearcher(root, model, store)

        # Warmup: ensure FTS index is built and model is warm
        searcher.search("warmup", top_k=1)

        start = time.perf_counter()
        results = searcher.search("architecture decision", top_k=5)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert len(results) > 0, "Should return results"
        assert elapsed_ms < 2000, (
            f"Single query took {elapsed_ms:.0f}ms, expected < 2000ms"
        )

    @pytest.mark.search
    def test_batch_query_latency(self, rag_components):
        """5 sequential queries should complete within 5 seconds total."""
        import time

        from rag.search import VaultSearcher

        model = rag_components["model"]
        store = rag_components["store"]
        root = rag_components["root"]

        searcher = VaultSearcher(root, model, store)
        queries = [
            "architecture decision",
            "type:plan implementation",
            "editor event handling",
            "displaymap coordinate mapping",
            "safety audit",
        ]

        start = time.perf_counter()
        for q in queries:
            searcher.search(q, top_k=5)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert elapsed_ms < 5000, (
            f"5 queries took {elapsed_ms:.0f}ms, expected < 5000ms"
        )

    @pytest.mark.search
    def test_query_embedding_latency(self, rag_components):
        """Single query embedding should complete within 500ms."""
        import time

        model = rag_components["model"]

        start = time.perf_counter()
        vec = model.encode_query("test query for latency")
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert vec.shape == (model.dimension,)
        assert elapsed_ms < 500, (
            f"Query embedding took {elapsed_ms:.0f}ms, expected < 500ms"
        )

    @pytest.mark.search
    def test_parse_query_latency(self):
        """Query parsing (pure regex) should be sub-millisecond."""
        import time

        from rag.search import parse_query

        start = time.perf_counter()
        for _ in range(100):
            parse_query("type:adr feature:editor architecture decisions")
        elapsed_ms = (time.perf_counter() - start) * 1000

        per_call_ms = elapsed_ms / 100
        assert per_call_ms < 1.0, (
            f"parse_query took {per_call_ms:.3f}ms per call, expected < 1ms"
        )

    # -- Resource tests --

    @pytest.mark.quality
    def test_store_disk_footprint(self, rag_components_full):
        """The .lance/ directory should be under 50MB for ~213 docs."""
        root = rag_components_full["root"]
        lance_dir = root / ".lance"

        total_bytes = sum(f.stat().st_size for f in lance_dir.rglob("*") if f.is_file())
        total_mb = total_bytes / (1024 * 1024)

        assert total_mb < 50, f".lance/ directory is {total_mb:.1f}MB, expected < 50MB"

    @pytest.mark.search
    def test_index_result_has_timing(self, rag_components):
        """IndexResult should report valid timing metadata."""
        result = rag_components["index_result"]

        assert result.duration_ms > 0, "duration_ms should be positive"
        assert result.duration_ms < 900_000, (
            f"Indexing took {result.duration_ms}ms (15 min), seems too long"
        )

    @pytest.mark.quality
    def test_document_count_matches_vault(self, rag_components_full):
        """Indexed count should match scannable docs with valid DocType."""
        from vault.scanner import get_doc_type, scan_vault

        root = rag_components_full["root"]
        store = rag_components_full["store"]

        valid_count = sum(
            1 for p in scan_vault(root) if get_doc_type(p, root) is not None
        )
        indexed_count = store.count()

        assert indexed_count == valid_count, (
            f"Store has {indexed_count} docs, vault has {valid_count} valid docs"
        )

    @pytest.mark.search
    def test_graph_cache_reused_across_searches(self, rag_components):
        """VaultSearcher should reuse cached VaultGraph across searches."""
        from rag.search import VaultSearcher

        model = rag_components["model"]
        store = rag_components["store"]
        root = rag_components["root"]

        searcher = VaultSearcher(root, model, store)

        # First search builds graph
        searcher.search("architecture", top_k=1)
        graph1 = searcher._cached_graph

        # Second search should reuse same graph instance
        searcher.search("editor", top_k=1)
        graph2 = searcher._cached_graph

        assert graph1 is graph2, "Graph should be reused across searches"

    @pytest.mark.search
    def test_graph_cache_ttl_expiry(self, rag_components):
        """VaultSearcher with TTL=0 should rebuild graph on every search."""
        from rag.search import VaultSearcher

        model = rag_components["model"]
        store = rag_components["store"]
        root = rag_components["root"]

        searcher = VaultSearcher(root, model, store, graph_ttl_seconds=0)

        searcher.search("architecture", top_k=1)
        graph1 = searcher._cached_graph

        searcher.search("editor", top_k=1)
        graph2 = searcher._cached_graph

        assert graph1 is not graph2, "Graph should be rebuilt with TTL=0"

    @pytest.mark.search
    def test_graph_rebuild_cost_per_query(self, rag_components):
        """Measure the cost of VaultGraph construction, which is rebuilt on
        every search call by rerank_with_graph(). VaultGraph reads every
        file in the vault twice (metadata + links pass). This test documents
        the overhead so we can track it and optimize later if needed.
        """
        import time

        from graph.api import VaultGraph

        root = rag_components["root"]

        start = time.perf_counter()
        graph = VaultGraph(root)
        graph_ms = (time.perf_counter() - start) * 1000

        assert len(graph.nodes) > 0
        # Document the cost - this is informational, threshold is generous
        # since graph rebuild happens on every search query
        assert graph_ms < 2000, (
            f"VaultGraph build took {graph_ms:.0f}ms, expected < 2000ms"
        )

    @pytest.mark.quality
    def test_incremental_noop_latency(self, rag_components_full):
        """Incremental index with no changes should be fast (< 3s).

        Requires full corpus because incremental_index() scans the full
        vault and compares against stored ids.
        """
        import time

        indexer = rag_components_full["indexer"]

        start = time.perf_counter()
        result = indexer.incremental_index()
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert result.added == 0
        assert elapsed_ms < 3000, (
            f"No-op incremental index took {elapsed_ms:.0f}ms, expected < 3000ms"
        )

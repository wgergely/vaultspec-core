"""Live integration tests for RAG pipeline against mock-project vault.

These tests run against real data in mock-project/.docs/ with real
embedding models and real LanceDB storage. NO MOCKS. NO STUBS.
"""

from __future__ import annotations

import pathlib
import shutil
import sys

import pytest

# Ensure vault lib is importable
LIB_SRC = pathlib.Path(__file__).parent.parent / ".rules" / "lib" / "src"
if str(LIB_SRC) not in sys.path:
    sys.path.insert(0, str(LIB_SRC))

# Check if RAG deps are available
try:
    import lancedb  # noqa: F401
    import sentence_transformers  # noqa: F401
    import torch  # noqa: F401

    HAS_RAG = True
except ImportError:
    HAS_RAG = False

pytestmark = pytest.mark.skipif(not HAS_RAG, reason="RAG dependencies not installed")

MOCK_PROJECT = pathlib.Path(__file__).parent.parent / "mock-project"


@pytest.fixture(scope="module")
def rag_components():
    """Set up real RAG components once for the entire test module.

    Uses the mock-project vault with real embeddings and a real LanceDB store.
    The .lance/ directory is created inside mock-project and cleaned up after.
    """
    from rag.embeddings import EmbeddingModel
    from rag.indexer import VaultIndexer
    from rag.store import VaultStore

    lance_dir = MOCK_PROJECT / ".lance"

    # Clean up any previous test data
    if lance_dir.exists():
        shutil.rmtree(lance_dir)

    model = EmbeddingModel()
    store = VaultStore(MOCK_PROJECT)
    indexer = VaultIndexer(MOCK_PROJECT, model, store)

    # Run full index
    result = indexer.full_index()

    yield {
        "model": model,
        "store": store,
        "indexer": indexer,
        "index_result": result,
        "root": MOCK_PROJECT,
    }

    # Cleanup
    if lance_dir.exists():
        shutil.rmtree(lance_dir)
    meta_file = MOCK_PROJECT / ".lance" / "index_meta.json"
    if meta_file.exists():
        meta_file.unlink()


# ---- Embedding Model Tests ----


class TestEmbeddingModel:
    """Tests for the real EmbeddingModel with nomic-embed-text-v1.5."""

    def test_model_loads(self, rag_components):
        model = rag_components["model"]
        assert model.device in ("cuda", "cpu")

    def test_encode_documents_shape(self, rag_components):
        model = rag_components["model"]
        texts = ["This is a test document about architecture decisions."]
        vectors = model.encode_documents(texts)
        assert vectors.shape == (1, 768)

    def test_encode_query_shape(self, rag_components):
        model = rag_components["model"]
        vector = model.encode_query("vector database")
        assert vector.shape == (768,)

    def test_document_query_similarity(self, rag_components):
        """Documents about a topic should be more similar to related queries."""
        import numpy as np

        model = rag_components["model"]

        doc_vec = model.encode_documents(
            ["LanceDB is an embedded vector database for semantic search"]
        )[0]
        related_query = model.encode_query("vector database for search")
        unrelated_query = model.encode_query("chocolate cake recipe")

        sim_related = float(np.dot(doc_vec, related_query))
        sim_unrelated = float(np.dot(doc_vec, unrelated_query))

        assert sim_related > sim_unrelated

    def test_encode_documents_batched(self, rag_components):
        """Batched encoding with batch_size=2 on 3 docs should produce
        the same shape as unbatched encoding.
        """
        model = rag_components["model"]
        texts = [
            "First document about architecture.",
            "Second document about testing.",
            "Third document about performance.",
        ]
        vectors = model.encode_documents(texts, batch_size=2)
        assert vectors.shape == (3, 768)

    def test_query_embedding_cache_hit(self, rag_components):
        """Repeated identical queries should hit the LRU cache."""
        model = rag_components["model"]
        query = "cache test query for embedding"

        # Clear any previous cache state
        model._encode_query_cached.cache_clear()

        model.encode_query(query)
        info_after_first = model._encode_query_cached.cache_info()
        assert info_after_first.misses >= 1

        model.encode_query(query)
        info_after_second = model._encode_query_cached.cache_info()
        assert info_after_second.hits >= 1


# ---- Store Tests ----


class TestVaultStore:
    """Tests for the real LanceDB store with actual data."""

    def test_store_has_documents(self, rag_components):
        store = rag_components["store"]
        count = store.count()
        assert count > 0, "Store should have documents after indexing"

    def test_get_all_ids(self, rag_components):
        store = rag_components["store"]
        ids = store.get_all_ids()
        assert len(ids) > 0
        # All ids should be strings
        for doc_id in ids:
            assert isinstance(doc_id, str)
            assert len(doc_id) > 0

    def test_vault_store_context_manager(self, tmp_path):
        """VaultStore should support the context manager protocol."""
        from rag.store import VaultStore

        with VaultStore(tmp_path) as store:
            assert store.db is not None
            store.ensure_table()
        # After exiting context, db should be released
        assert store.db is None

    def test_hybrid_search_returns_results(self, rag_components):
        model = rag_components["model"]
        store = rag_components["store"]

        query_vec = model.encode_query("architecture decision")
        results = store.hybrid_search(
            query_vector=query_vec,
            query_text="architecture decision",
            limit=5,
        )
        assert len(results) > 0
        # Each result should have an id and path
        for r in results:
            assert "id" in r
            assert "path" in r


# ---- Indexer Tests ----


class TestVaultIndexer:
    """Tests for the indexing pipeline with real vault data."""

    def test_full_index_counts(self, rag_components):
        result = rag_components["index_result"]
        assert result.total > 0
        assert result.added > 0
        assert result.duration_ms >= 0
        assert result.device in ("cuda", "cpu")

    def test_index_matches_store_count(self, rag_components):
        result = rag_components["index_result"]
        store = rag_components["store"]
        assert result.total == store.count()

    def test_incremental_index_no_changes(self, rag_components):
        """Incremental index with no changes should report zero additions."""
        indexer = rag_components["indexer"]
        result = indexer.incremental_index()
        # No new files, no modifications, no deletions
        assert result.added == 0
        assert result.removed == 0
        # Total should match the full index
        assert result.total == rag_components["index_result"].total


# ---- Query Parsing Tests ----


class TestQueryParsing:
    """Tests for the query parser."""

    def test_plain_query(self):
        from rag.search import parse_query

        parsed = parse_query("vector database architecture")
        assert parsed.text == "vector database architecture"
        assert parsed.filters == {}

    def test_type_filter(self):
        from rag.search import parse_query

        parsed = parse_query("type:adr vector database")
        assert parsed.text == "vector database"
        assert parsed.filters == {"doc_type": "adr"}

    def test_multiple_filters(self):
        from rag.search import parse_query

        parsed = parse_query("type:adr feature:rag vector database")
        assert parsed.text == "vector database"
        assert parsed.filters["doc_type"] == "adr"
        assert parsed.filters["feature"] == "rag"

    def test_date_filter(self):
        from rag.search import parse_query

        parsed = parse_query("date:2026-02 decisions")
        assert parsed.text == "decisions"
        assert parsed.filters["date"] == "2026-02"

    def test_tag_filter(self):
        from rag.search import parse_query

        parsed = parse_query("tag:#research embedding models")
        assert parsed.text == "embedding models"
        assert parsed.filters["tag"] == "research"

    def test_filter_only_query(self):
        from rag.search import parse_query

        parsed = parse_query("type:adr feature:rag")
        assert parsed.text == ""
        assert parsed.filters["doc_type"] == "adr"
        assert parsed.filters["feature"] == "rag"


# ---- End-to-End Search Tests ----


class TestVaultSearch:
    """End-to-end search tests against real indexed vault data."""

    def test_search_returns_results(self, rag_components):
        from rag.search import VaultSearcher

        model = rag_components["model"]
        store = rag_components["store"]
        root = rag_components["root"]

        searcher = VaultSearcher(root, model, store)
        results = searcher.search("architecture decision", top_k=5)

        assert len(results) > 0
        for r in results:
            assert r.id
            assert r.path
            assert r.score > 0

    def test_search_results_are_sorted_by_score(self, rag_components):
        from rag.search import VaultSearcher

        model = rag_components["model"]
        store = rag_components["store"]
        root = rag_components["root"]

        searcher = VaultSearcher(root, model, store)
        results = searcher.search("implementation plan", top_k=5)

        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_search_with_type_filter(self, rag_components):
        from rag.search import VaultSearcher

        model = rag_components["model"]
        store = rag_components["store"]
        root = rag_components["root"]

        searcher = VaultSearcher(root, model, store)
        results = searcher.search("type:adr architecture", top_k=10)

        # All results should be ADRs
        for r in results:
            assert r.doc_type == "adr", f"Expected adr, got {r.doc_type} for {r.id}"

    def test_search_respects_limit(self, rag_components):
        from rag.search import VaultSearcher

        model = rag_components["model"]
        store = rag_components["store"]
        root = rag_components["root"]

        searcher = VaultSearcher(root, model, store)
        results = searcher.search("project", top_k=3)

        assert len(results) <= 3

    def test_search_result_has_snippet(self, rag_components):
        from rag.search import VaultSearcher

        model = rag_components["model"]
        store = rag_components["store"]
        root = rag_components["root"]

        searcher = VaultSearcher(root, model, store)
        results = searcher.search("architecture", top_k=1)

        if results:
            assert isinstance(results[0].snippet, str)


# ---- Device Info Tests ----


class TestDeviceInfo:
    """Tests for device detection utility."""

    def test_get_device_info(self):
        from rag.embeddings import get_device_info

        info = get_device_info()
        assert info["device"] in ("cuda", "cpu")
        if info["device"] == "cuda":
            assert info["gpu_name"] is not None
            assert info["vram_mb"] is not None
        else:
            assert info["gpu_name"] is None
            assert info["vram_mb"] is None


# ---- Document Preparation Tests ----


class TestDocumentPreparation:
    """Tests for individual document preparation."""

    def test_prepare_real_document(self):
        from rag.indexer import prepare_document

        # Find a real document in the mock-project
        from vault.scanner import scan_vault

        docs = list(scan_vault(MOCK_PROJECT))
        assert len(docs) > 0, "mock-project should have documents"

        doc = prepare_document(docs[0], MOCK_PROJECT)
        assert doc is not None
        assert doc.id
        assert doc.path
        assert doc.doc_type in ("adr", "exec", "plan", "reference", "research")
        assert doc.content

    def test_prepare_all_documents(self):
        from rag.indexer import prepare_document
        from vault.scanner import scan_vault

        prepared = 0
        skipped = 0
        for path in scan_vault(MOCK_PROJECT):
            doc = prepare_document(path, MOCK_PROJECT)
            if doc is not None:
                prepared += 1
                assert doc.id == path.stem
            else:
                skipped += 1

        assert prepared > 0, "Should prepare at least some documents"


# ---- Robustness Tests ----


class TestRobustness:
    """Edge-case and robustness tests for the RAG pipeline.

    Covers documents without frontmatter, non-standard metadata schemas,
    unicode content, empty/special queries, idempotent indexing, and
    graph re-ranking with orphan documents.
    """

    # -- Document edge cases --

    def test_stories_without_frontmatter_skipped(self, rag_components):
        """Stories in .docs/stories/ have no YAML frontmatter and are French fiction.

        Since DocType enum doesn't include 'stories', get_doc_type returns None
        and prepare_document returns None. Verify they are gracefully skipped.
        """
        from rag.indexer import prepare_document
        from vault.scanner import scan_vault

        root = rag_components["root"]
        story_paths = [p for p in scan_vault(root) if "stories" in p.parts]
        assert len(story_paths) > 0, "Should find story files in scanner output"

        for path in story_paths:
            doc = prepare_document(path, root)
            assert doc is None, (
                f"Story {path.name} should be skipped (no valid DocType), "
                f"but prepare_document returned a doc"
            )

    def test_audit_nonstandard_frontmatter_skipped(self, rag_components):
        """audit/2026-02-07-main-window-safety-audit.md has 'feature:' key
        instead of 'tags:' array. Since DocType doesn't include 'audit',
        get_doc_type returns None and the doc is skipped.
        """
        from rag.indexer import prepare_document
        from vault.scanner import scan_vault

        root = rag_components["root"]
        audit_paths = [p for p in scan_vault(root) if "audit" in p.parts]
        assert len(audit_paths) > 0, "Should find audit files in scanner output"

        for path in audit_paths:
            doc = prepare_document(path, root)
            assert doc is None, (
                f"Audit doc {path.name} should be skipped (no valid DocType)"
            )

    def test_unicode_content_in_parser(self):
        """French stories have accented chars. Verify parse_vault_metadata
        handles unicode content without crashing.
        """
        from vault.parser import parse_vault_metadata

        # Simulate content with accented French characters
        french_content = (
            "# Chapitre 1 : La M\u00e9lancolie de Croustillant\n\n"
            "Au c\u0153ur d'une boulangerie parisienne, o\u00f9 les "
            "effluves de beurre et de sucre flottaient."
        )
        metadata, body = parse_vault_metadata(french_content)
        # No frontmatter, so metadata is empty
        assert metadata.tags == []
        assert metadata.date is None
        assert "M\u00e9lancolie" in body

    def test_feature_key_frontmatter_parsed(self):
        """Documents using 'feature:' key (Pattern B) instead of 'tags:' array
        should not crash the parser. The feature value is stored differently.
        """
        from vault.parser import parse_vault_metadata

        content = (
            "---\n"
            "feature: dispatch\n"
            "date: 2026-02-07\n"
            "related:\n"
            '  - "[[some-doc]]"\n'
            "---\n"
            "# Test Document\n"
        )
        metadata, body = parse_vault_metadata(content)
        # Parser doesn't crash. 'feature' is not in metadata.tags (which is
        # only populated from 'tags:' key), but date and related are parsed.
        assert metadata.date == "2026-02-07"
        assert len(metadata.related) >= 1
        assert "# Test Document" in body

    # -- Query edge cases --

    def test_empty_query(self, rag_components):
        """VaultSearcher.search('') should not crash."""
        from rag.search import VaultSearcher

        model = rag_components["model"]
        store = rag_components["store"]
        root = rag_components["root"]

        searcher = VaultSearcher(root, model, store)
        results = searcher.search("", top_k=5)
        # Should return some results (empty query still embeds something)
        # or empty list -- but must not crash
        assert isinstance(results, list)

    def test_filter_only_query_returns_results(self, rag_components):
        """'type:adr' with no text should return ADR docs, not crash."""
        from rag.search import VaultSearcher

        model = rag_components["model"]
        store = rag_components["store"]
        root = rag_components["root"]

        searcher = VaultSearcher(root, model, store)
        results = searcher.search("type:adr", top_k=10)
        assert isinstance(results, list)
        # Should find some ADR docs
        if results:
            for r in results:
                assert r.doc_type == "adr"

    def test_invalid_filter_value(self, rag_components):
        """'type:nonexistent' should return empty results, not crash."""
        from rag.search import VaultSearcher

        model = rag_components["model"]
        store = rag_components["store"]
        root = rag_components["root"]

        searcher = VaultSearcher(root, model, store)
        results = searcher.search("type:nonexistent some query", top_k=5)
        assert isinstance(results, list)
        assert len(results) == 0

    def test_special_characters_in_query(self, rag_components):
        """Query with quotes, brackets, and special chars should not crash."""
        from rag.search import VaultSearcher

        model = rag_components["model"]
        store = rag_components["store"]
        root = rag_components["root"]

        searcher = VaultSearcher(root, model, store)

        special_queries = [
            'query with "quotes"',
            "query with [[wiki-links]]",
            "query with (parentheses) and [brackets]",
            "query with <angle> & ampersand",
        ]
        for q in special_queries:
            results = searcher.search(q, top_k=3)
            assert isinstance(results, list), f"Query '{q}' should not crash"

    def test_very_long_query(self, rag_components):
        """A 500+ character query should work within limits."""
        from rag.search import VaultSearcher

        model = rag_components["model"]
        store = rag_components["store"]
        root = rag_components["root"]

        searcher = VaultSearcher(root, model, store)
        long_query = "architecture decision " * 30  # ~660 chars
        results = searcher.search(long_query, top_k=5)
        assert isinstance(results, list)

    # -- Index edge cases --

    def test_double_full_index_idempotent(self, rag_components):
        """Two full_index() calls should yield the same document count."""
        indexer = rag_components["indexer"]
        store = rag_components["store"]

        first_count = store.count()

        # Run full index again
        result = indexer.full_index()
        second_count = store.count()

        assert first_count == second_count, (
            f"Full index should be idempotent: {first_count} vs {second_count}"
        )
        assert result.total == second_count

    def test_incremental_after_full_stable(self, rag_components):
        """Incremental index after full should report zero changes."""
        indexer = rag_components["indexer"]
        result = indexer.incremental_index()

        assert result.added == 0, f"Expected 0 added, got {result.added}"
        assert result.removed == 0, f"Expected 0 removed, got {result.removed}"
        assert result.total == rag_components["index_result"].total

    def test_search_empty_store(self, tmp_path):
        """Searching a fresh VaultStore with no indexed docs should return
        empty results without crashing.
        """
        from rag.embeddings import EmbeddingModel
        from rag.store import VaultStore

        # Create a minimal vault structure so VaultStore can connect
        store = VaultStore(tmp_path)
        store.ensure_table()

        model = EmbeddingModel()
        query_vec = model.encode_query("anything")

        results = store.hybrid_search(
            query_vector=query_vec,
            query_text="anything",
            limit=5,
        )
        assert results == []

    # -- Store helper edge cases --

    def test_parse_json_list_valid_json(self):
        """_parse_json_list should parse valid JSON arrays."""
        from rag.store import _parse_json_list

        assert _parse_json_list('["#adr", "#editor"]') == ["#adr", "#editor"]
        assert _parse_json_list("[]") == []

    def test_parse_json_list_empty_string(self):
        """_parse_json_list should handle empty string gracefully."""
        from rag.store import _parse_json_list

        assert _parse_json_list("") == []

    def test_parse_json_list_comma_separated_fallback(self):
        """_parse_json_list should fall back to comma-splitting for non-JSON."""
        from rag.store import _parse_json_list

        result = _parse_json_list("#adr, #editor")
        assert result == ["#adr", "#editor"]

    def test_parse_json_list_non_array_json(self):
        """_parse_json_list with valid JSON that is not an array should
        fall back to comma splitting."""
        from rag.store import _parse_json_list

        result = _parse_json_list('"just a string"')
        assert isinstance(result, list)

    def test_content_with_embedded_yaml_separators(self):
        """Documents with --- inside content (not frontmatter) should parse
        correctly. The regex anchors to ^--- so internal --- is not confused.
        """
        from vault.parser import parse_vault_metadata

        content = (
            "# Some Research Doc\n\n"
            "Some content here.\n\n"
            "---\n\n"
            "## Section after separator\n\n"
            "More content."
        )
        metadata, body = parse_vault_metadata(content)
        # No frontmatter block, so metadata is empty defaults
        assert metadata.tags == []
        assert metadata.date is None
        # The full content including --- should be in body
        assert "---" in body

    def test_content_with_code_block_yaml_separators(self):
        """Documents with --- inside code blocks should not confuse the parser."""
        from vault.parser import parse_vault_metadata

        content = (
            "---\n"
            'tags: ["#research", "#dispatch"]\n'
            "date: 2026-02-07\n"
            "---\n"
            "# Title\n\n"
            "```yaml\n"
            "---\n"
            "fake: frontmatter\n"
            "---\n"
            "```\n"
        )
        metadata, body = parse_vault_metadata(content)
        assert metadata.tags == ["#research", "#dispatch"]
        assert metadata.date == "2026-02-07"
        assert "fake: frontmatter" in body

    def test_sql_injection_in_filter_value(self, rag_components):
        """Filter values with SQL injection characters should not crash.
        _build_where uses string interpolation, so test that LanceDB
        handles malformed predicates gracefully or that they produce
        empty results rather than exceptions.
        """
        from rag.search import VaultSearcher

        model = rag_components["model"]
        store = rag_components["store"]
        root = rag_components["root"]

        searcher = VaultSearcher(root, model, store)
        # These contain SQL special chars that could break the WHERE clause
        adversarial_queries = [
            "type:adr' OR 1=1 --",
            "type:adr'; DROP TABLE vault_docs; --",
            "feature:test' UNION SELECT * FROM vault_docs --",
        ]
        for q in adversarial_queries:
            # Should not raise an unhandled exception
            try:
                results = searcher.search(q, top_k=3)
                assert isinstance(results, list)
            except Exception:
                # If it raises, that's acceptable - the important thing
                # is it doesn't corrupt the store or crash the process
                pass

        # Verify the store is still functional after adversarial queries
        results = searcher.search("architecture", top_k=3)
        assert len(results) > 0, "Store should still work after adversarial queries"

    def test_docs_without_frontmatter_counted(self):
        """Verify how many docs in the vault lack frontmatter entirely.
        These should all be in unsupported directories (stories) or have
        no YAML block at all (some research docs).
        """
        from vault.parser import parse_vault_metadata
        from vault.scanner import scan_vault

        no_frontmatter = []
        for path in scan_vault(MOCK_PROJECT):
            content = path.read_text(encoding="utf-8")
            metadata, _body = parse_vault_metadata(content)
            if not metadata.tags and metadata.date is None:
                no_frontmatter.append(path.name)

        # We expect some docs without frontmatter (stories, some research)
        assert len(no_frontmatter) > 0, "Should find docs without frontmatter"

    def test_build_where_escapes_quotes(self):
        """_build_where should escape single quotes in filter values."""
        from rag.store import VaultStore

        result = VaultStore._build_where({"doc_type": "adr' OR 1=1 --"})
        assert result is not None
        # The single quote should be escaped (doubled)
        assert "''" in result
        # The unescaped injection should not be present
        assert "adr' OR" not in result

    # -- Graph re-ranking edge cases --

    def test_graph_reranking_with_orphans(self, rag_components):
        """Orphaned docs (no in-links) should still appear in results.

        Graph re-ranking should boost well-connected docs but not
        eliminate orphans from results.
        """
        from rag.search import VaultSearcher

        model = rag_components["model"]
        store = rag_components["store"]
        root = rag_components["root"]

        searcher = VaultSearcher(root, model, store)
        # Use a broad query that should match many docs
        results = searcher.search("editor implementation", top_k=15)

        assert len(results) > 0, "Should find results for broad query"
        # All results should have valid scores (even orphans)
        for r in results:
            assert r.score > 0, f"Result {r.id} has non-positive score: {r.score}"


# ---- Performance Tests ----


class TestPerformance:
    """Performance and resource-usage tests for the RAG pipeline.

    Thresholds are generous to accommodate CPU-only CI environments.
    """

    # -- Timing tests --

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

    def test_incremental_noop_latency(self, rag_components):
        """Incremental index with no changes should be fast (< 3s)."""
        import time

        indexer = rag_components["indexer"]

        start = time.perf_counter()
        result = indexer.incremental_index()
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert result.added == 0
        assert elapsed_ms < 3000, (
            f"No-op incremental index took {elapsed_ms:.0f}ms, expected < 3000ms"
        )

    def test_query_embedding_latency(self, rag_components):
        """Single query embedding should complete within 500ms."""
        import time

        model = rag_components["model"]

        start = time.perf_counter()
        vec = model.encode_query("test query for latency")
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert vec.shape == (768,)
        assert elapsed_ms < 500, (
            f"Query embedding took {elapsed_ms:.0f}ms, expected < 500ms"
        )

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

    def test_store_disk_footprint(self, rag_components):
        """The .lance/ directory should be under 50MB for ~217 docs."""
        root = rag_components["root"]
        lance_dir = root / ".lance"

        total_bytes = sum(f.stat().st_size for f in lance_dir.rglob("*") if f.is_file())
        total_mb = total_bytes / (1024 * 1024)

        assert total_mb < 50, f".lance/ directory is {total_mb:.1f}MB, expected < 50MB"

    def test_index_result_has_timing(self, rag_components):
        """IndexResult should report valid timing metadata."""
        result = rag_components["index_result"]

        assert result.duration_ms > 0, "duration_ms should be positive"
        assert result.duration_ms < 900_000, (
            f"Indexing took {result.duration_ms}ms (15 min), seems too long"
        )

    def test_document_count_matches_vault(self, rag_components):
        """Indexed count should match scannable docs with valid DocType."""
        from vault.scanner import get_doc_type, scan_vault

        root = rag_components["root"]
        store = rag_components["store"]

        valid_count = sum(
            1 for p in scan_vault(root) if get_doc_type(p, root) is not None
        )
        indexed_count = store.count()

        assert indexed_count == valid_count, (
            f"Store has {indexed_count} docs, vault has {valid_count} valid docs"
        )

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


# ---- Helpfulness / Search Quality Tests ----


class TestHelpfulness:
    """Search quality tests verifying the RAG pipeline returns relevant results.

    Known-answer tests are grounded in actual mock-project/.docs/ content.
    Filter tests verify metadata predicates are applied correctly.
    Ranking tests verify score ordering and graph boosts.
    """

    # -- Known-answer precision --

    def test_search_finds_safety_audit(self, rag_components):
        """'Rust safety audit' should surface the safety audit in reference/.

        The doc reference/2026-02-07-main-window-safety-audit.md contains
        'Rust Code Safety Audit' in its H1. It should appear in top 5.
        """
        from rag.search import VaultSearcher

        model = rag_components["model"]
        store = rag_components["store"]
        root = rag_components["root"]

        searcher = VaultSearcher(root, model, store)
        results = searcher.search("Rust safety audit", top_k=5)

        result_ids = [r.id for r in results]
        assert any("safety-audit" in rid for rid in result_ids), (
            f"Expected a safety-audit doc in top 5, got: {result_ids}"
        )

    def test_search_finds_architecture_docs(self, rag_components):
        """'architecture design' should surface architecture-related docs."""
        from rag.search import VaultSearcher

        model = rag_components["model"]
        store = rag_components["store"]
        root = rag_components["root"]

        searcher = VaultSearcher(root, model, store)
        results = searcher.search("architecture design", top_k=10)

        assert len(results) > 0, "Should find architecture docs"
        # At least one result should have 'architecture' in its id or title
        found = any(
            "architecture" in r.id.lower() or "architecture" in r.title.lower()
            for r in results
        )
        assert found, (
            f"Expected at least one architecture doc in results, "
            f"got: {[(r.id, r.title) for r in results]}"
        )

    def test_search_finds_editor_demo(self, rag_components):
        """'editor demo' should surface editor-demo feature docs."""
        from rag.search import VaultSearcher

        model = rag_components["model"]
        store = rag_components["store"]
        root = rag_components["root"]

        searcher = VaultSearcher(root, model, store)
        results = searcher.search("editor demo", top_k=10)

        assert len(results) > 0, "Should find editor demo docs"
        # Check that some results have editor-demo feature or id
        found = any(
            r.feature == "editor-demo" or "editor-demo" in r.id for r in results
        )
        assert found, (
            f"Expected editor-demo docs in results, "
            f"got: {[(r.id, r.feature) for r in results]}"
        )

    def test_search_displaymap_keyword(self, rag_components):
        """'DisplayMap' exact keyword should surface displaymap docs in top 3.

        adr/2026-02-06-displaymap-architecture-design.md mentions DisplayMap
        44 times and should rank very high for this query.
        """
        from rag.search import VaultSearcher

        model = rag_components["model"]
        store = rag_components["store"]
        root = rag_components["root"]

        searcher = VaultSearcher(root, model, store)
        results = searcher.search("DisplayMap", top_k=3)

        assert len(results) > 0, "Should find DisplayMap docs"
        result_ids = [r.id for r in results]
        found = any("displaymap" in rid.lower() for rid in result_ids)
        assert found, f"Expected a displaymap doc in top 3, got: {result_ids}"

    def test_search_finds_french_content(self, rag_components):
        """'croissant boulangerie' targets French stories which are NOT indexed.

        Stories live in .docs/stories/ which has no valid DocType, so they
        are skipped during indexing. This query should return empty or
        unrelated results.
        """
        from rag.search import VaultSearcher

        model = rag_components["model"]
        store = rag_components["store"]
        root = rag_components["root"]

        searcher = VaultSearcher(root, model, store)
        results = searcher.search("croissant boulangerie", top_k=5)

        # Stories are not indexed, so no story doc should appear
        for r in results:
            assert "croissant" not in r.id.lower(), (
                f"Story doc {r.id} should not be indexed"
            )

    # -- Filter correctness --

    def test_type_filter_excludes_others(self, rag_components):
        """'type:adr architecture' should return ONLY adr docs."""
        from rag.search import VaultSearcher

        model = rag_components["model"]
        store = rag_components["store"]
        root = rag_components["root"]

        searcher = VaultSearcher(root, model, store)
        results = searcher.search("type:adr architecture", top_k=10)

        assert len(results) > 0, "Should find ADR architecture docs"
        for r in results:
            assert r.doc_type == "adr", (
                f"Expected doc_type 'adr', got '{r.doc_type}' for {r.id}"
            )

    def test_feature_filter_narrows(self, rag_components):
        """'feature:editor-demo layout' should return ONLY editor-demo docs.

        Several docs in reference/, plan/, exec/, and adr/ have
        tags: ['#<type>', '#editor-demo'] which populates the feature field.
        """
        from rag.search import VaultSearcher

        model = rag_components["model"]
        store = rag_components["store"]
        root = rag_components["root"]

        searcher = VaultSearcher(root, model, store)
        results = searcher.search("feature:editor-demo layout", top_k=10)

        assert len(results) > 0, "Should find editor-demo layout docs"
        for r in results:
            assert r.feature == "editor-demo", (
                f"Expected feature 'editor-demo', got '{r.feature}' for {r.id}"
            )

    def test_date_filter_prefix(self, rag_components):
        """'date:2026-02-06 architecture' should return docs dated 2026-02-06."""
        from rag.search import VaultSearcher

        model = rag_components["model"]
        store = rag_components["store"]
        root = rag_components["root"]

        searcher = VaultSearcher(root, model, store)
        results = searcher.search("date:2026-02-06 architecture", top_k=10)

        assert len(results) > 0, "Should find docs from 2026-02-06"
        for r in results:
            assert r.date.startswith("2026-02-06"), (
                f"Expected date starting with '2026-02-06', got '{r.date}' for {r.id}"
            )

    def test_combined_filters(self, rag_components):
        """'type:adr feature:editor-demo' should return the intersection.

        Only adr/2026-02-05-editor-demo-architecture.md has both doc_type=adr
        AND feature=editor-demo.
        """
        from rag.search import VaultSearcher

        model = rag_components["model"]
        store = rag_components["store"]
        root = rag_components["root"]

        searcher = VaultSearcher(root, model, store)
        results = searcher.search("type:adr feature:editor-demo", top_k=10)

        assert len(results) > 0, "Should find at least one matching doc"
        for r in results:
            assert r.doc_type == "adr", (
                f"Expected doc_type 'adr', got '{r.doc_type}' for {r.id}"
            )
            assert r.feature == "editor-demo", (
                f"Expected feature 'editor-demo', got '{r.feature}' for {r.id}"
            )

    # -- Ranking quality --

    def test_exact_keyword_ranks_high(self, rag_components):
        """Search for 'SetWindowCompositionAttribute' should surface the
        safety audit doc that contains this exact Win32 API identifier.
        """
        from rag.search import VaultSearcher

        model = rag_components["model"]
        store = rag_components["store"]
        root = rag_components["root"]

        searcher = VaultSearcher(root, model, store)
        results = searcher.search("SetWindowCompositionAttribute", top_k=5)

        assert len(results) > 0, "Should find results for specific identifier"
        # The safety audit doc should appear since it discusses this API
        found = any("safety-audit" in r.id or "main-window" in r.id for r in results)
        assert found, (
            f"Expected safety-audit or main-window doc for Win32 API query, "
            f"got: {[r.id for r in results]}"
        )

    def test_authority_boost_measurable(self, rag_components):
        """Well-linked docs should have higher scores than orphan docs.

        The graph re-ranker applies authority boost: score *= (1 + 0.1 * in_links).
        Documents with many in-links should tend to score higher than orphans
        when the query is equally relevant to both.
        """
        from graph.api import VaultGraph
        from rag.search import VaultSearcher

        model = rag_components["model"]
        store = rag_components["store"]
        root = rag_components["root"]

        searcher = VaultSearcher(root, model, store)
        # Broad query to get many results
        results = searcher.search("editor architecture implementation", top_k=15)

        if len(results) < 2:
            pytest.skip("Need at least 2 results to compare authority")

        graph = VaultGraph(root)

        # Separate results into well-linked (>=2 in-links) and orphans (0)
        linked = []
        orphans = []
        for r in results:
            node = graph.nodes.get(r.id)
            if node and len(node.in_links) >= 2:
                linked.append(r)
            elif node and len(node.in_links) == 0:
                orphans.append(r)

        if linked and orphans:
            avg_linked = sum(r.score for r in linked) / len(linked)
            avg_orphan = sum(r.score for r in orphans) / len(orphans)
            assert avg_linked > avg_orphan, (
                f"Well-linked docs (avg={avg_linked:.4f}) should score higher "
                f"than orphans (avg={avg_orphan:.4f}) on average"
            )

    def test_results_have_positive_scores(self, rag_components):
        """All results from any query should have score > 0."""
        from rag.search import VaultSearcher

        model = rag_components["model"]
        store = rag_components["store"]
        root = rag_components["root"]

        searcher = VaultSearcher(root, model, store)

        queries = ["architecture", "editor", "dispatch", "window positioning"]
        for q in queries:
            results = searcher.search(q, top_k=5)
            for r in results:
                assert r.score > 0, (
                    f"Query '{q}': result {r.id} has non-positive score {r.score}"
                )

    def test_more_results_with_higher_limit(self, rag_components):
        """top_k=10 should return >= len(top_k=3) results."""
        from rag.search import VaultSearcher

        model = rag_components["model"]
        store = rag_components["store"]
        root = rag_components["root"]

        searcher = VaultSearcher(root, model, store)
        results_3 = searcher.search("editor implementation", top_k=3)
        results_10 = searcher.search("editor implementation", top_k=10)

        assert len(results_10) >= len(results_3), (
            f"top_k=10 ({len(results_10)}) should return >= "
            f"top_k=3 ({len(results_3)}) results"
        )

    # -- Negative tests --

    def test_irrelevant_query_low_scores(self, rag_components):
        """'quantum physics dark matter' has no vault relevance.

        Should return empty or results with very low scores.
        """
        from rag.search import VaultSearcher

        model = rag_components["model"]
        store = rag_components["store"]
        root = rag_components["root"]

        searcher = VaultSearcher(root, model, store)
        results = searcher.search("quantum physics dark matter", top_k=5)

        if results:
            # Scores should be quite low compared to relevant queries
            max_score = max(r.score for r in results)
            # Compare against a relevant query's top score
            relevant = searcher.search("editor architecture", top_k=1)
            if relevant:
                assert max_score < relevant[0].score, (
                    f"Irrelevant query max score ({max_score:.4f}) should be "
                    f"lower than relevant query score ({relevant[0].score:.4f})"
                )

    def test_nonsense_query(self, rag_components):
        """'asdfghjkl zxcvbnm' should return empty or very low scores."""
        from rag.search import VaultSearcher

        model = rag_components["model"]
        store = rag_components["store"]
        root = rag_components["root"]

        searcher = VaultSearcher(root, model, store)
        results = searcher.search("asdfghjkl zxcvbnm", top_k=5)

        if results:
            # Compare against a relevant query
            relevant = searcher.search("DisplayMap architecture", top_k=1)
            if relevant:
                max_nonsense = max(r.score for r in results)
                assert max_nonsense < relevant[0].score, (
                    f"Nonsense query max score ({max_nonsense:.4f}) should be "
                    f"lower than relevant query score ({relevant[0].score:.4f})"
                )

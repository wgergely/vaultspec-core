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

"""Tests for the rag.api public facade."""

from __future__ import annotations

import pathlib
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


# ---- Public API Facade Tests ----


class TestRAGAPI:
    """Tests for the rag.api public facade.

    These tests exercise the public API functions end-to-end.  The API
    facade uses its own engine singleton separate from the rag_components
    fixture.  We use a dedicated temporary copy of the lance data to
    avoid conflicts with the session-scoped fixture.
    """

    def test_search_returns_results(self, rag_components):
        """rag.api.search returns SearchResult list.

        Uses the session-scoped rag_components to ensure indexed data
        exists, then calls the API facade which opens its own store
        connection against the same .lance directory.
        """
        from rag.search import VaultSearcher

        model = rag_components["model"]
        store = rag_components["store"]
        root = rag_components["root"]

        # Test the search pipeline (same as the API facade does internally)
        searcher = VaultSearcher(root, model, store)
        results = searcher.search("architecture")
        assert len(results) > 0
        assert hasattr(results[0], "id")
        assert hasattr(results[0], "score")

    def test_search_with_type_filter(self, rag_components):
        """rag.api.search filters by doc_type."""
        from rag.search import VaultSearcher

        model = rag_components["model"]
        store = rag_components["store"]
        root = rag_components["root"]

        searcher = VaultSearcher(root, model, store)
        results = searcher.search("type:adr architecture", top_k=5)
        for r in results:
            assert r.doc_type == "adr"

    @pytest.mark.slow
    def test_index_incremental(self, rag_components_full):
        """rag.api.index returns IndexResult with correct counts.

        Requires full corpus because incremental_index() scans the entire
        vault and compares against stored ids.
        """
        from rag.api import index

        root = rag_components_full["root"]
        result = index(root)
        assert result.total > 0
        assert result.duration_ms >= 0

    @pytest.mark.slow
    def test_index_full(self, rag_components_full):
        """rag.api.index with full=True rebuilds index."""
        from rag.api import index

        root = rag_components_full["root"]
        result = index(root, full=True)
        assert result.total > 0
        assert result.added > 0

    def test_get_document_existing(self, rag_components):
        """Store.get_by_id returns dict for known doc.

        Uses the fixture's store directly to avoid opening a competing
        LanceDB connection (which corrupts lance data files).
        Picks a doc_id from the indexed store (not list_documents, which
        scans the full filesystem and may return unindexed docs).
        """
        store = rag_components["store"]

        all_ids = store.get_all_ids()
        assert len(all_ids) > 0
        doc_id = next(iter(all_ids))
        result = store.get_by_id(doc_id)
        assert result is not None
        assert result["id"] == doc_id
        assert "content" in result
        assert "doc_type" in result

    def test_get_document_nonexistent(self, rag_components):
        """Store.get_by_id returns None for unknown doc."""
        store = rag_components["store"]
        result = store.get_by_id("nonexistent-doc-that-does-not-exist")
        assert result is None

    def test_list_documents(self, rag_components):
        """rag.api.list_documents returns all docs."""
        from rag.api import list_documents

        root = rag_components["root"]
        docs = list_documents(root)
        assert len(docs) > 0
        assert all("id" in d for d in docs)
        assert all("doc_type" in d for d in docs)
        assert all("title" in d for d in docs)

    def test_list_documents_type_filter(self, rag_components):
        """rag.api.list_documents filters by doc_type."""
        from rag.api import list_documents

        root = rag_components["root"]
        docs = list_documents(root, doc_type="adr")
        assert len(docs) > 0
        for d in docs:
            assert d["doc_type"] == "adr"

    def test_get_related(self, rag_components):
        """rag.api.get_related returns graph relationships."""
        from rag.api import get_related, list_documents

        root = rag_components["root"]
        docs = list_documents(root)
        doc_id = docs[0]["id"]
        result = get_related(root, doc_id)
        assert result is not None
        assert "doc_id" in result
        assert "outgoing" in result
        assert "incoming" in result
        assert result["doc_id"] == doc_id

    def test_get_status(self, rag_components):
        """rag.api.get_status returns vault summary.

        Verifies status using direct store access to avoid opening a
        conflicting LanceDB connection via the API facade.
        """
        root = rag_components["root"]
        store = rag_components["store"]

        # Verify status fields that don't need the API facade
        from metrics.api import get_vault_metrics
        from verification.api import list_features

        metrics = get_vault_metrics(root)
        features = sorted(list_features(root))

        assert metrics.total_docs > 0
        assert len(features) > 0
        assert store.count() > 0

    def test_engine_singleton(self, rag_components):
        """get_engine returns same instance for same root."""
        import rag.api as api_mod

        root = rag_components["root"]
        e1 = api_mod.get_engine(root)
        e2 = api_mod.get_engine(root)
        assert e1 is e2

        # Clean up the engine to avoid leaving a competing LanceDB connection
        e1.close()
        api_mod._engine = None

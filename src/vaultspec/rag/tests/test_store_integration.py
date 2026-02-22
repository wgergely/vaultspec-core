"""Integration tests for VaultStore: CRUD and hybrid search.

Unit tests for store helpers (_parse_json_list, _build_where) have been moved to:
src/vaultspec/rag/tests/test_store.py
"""

from __future__ import annotations

import importlib.util
import shutil

import pytest

from tests.constants import TEST_PROJECT

HAS_RAG = all(
    importlib.util.find_spec(pkg) is not None
    for pkg in ("lancedb", "sentence_transformers", "torch")
)

pytestmark = [
    pytest.mark.search,
    pytest.mark.skipif(not HAS_RAG, reason="RAG dependencies not installed"),
]


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

    def test_vault_store_context_manager(self):
        """VaultStore should support the context manager protocol."""
        from .. import VaultStore

        lance_dir = TEST_PROJECT / ".lance-test"
        try:
            with VaultStore(lance_dir) as store:
                assert store.db is not None
                store.ensure_table()
            # After exiting context, db should be released
            assert store.db is None
        finally:
            if lance_dir.exists():
                shutil.rmtree(lance_dir, ignore_errors=True)

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

    def test_search_empty_store(self):
        """Searching a fresh VaultStore with no indexed docs should return
        empty results without crashing.
        """
        from .. import EmbeddingModel, VaultStore

        lance_dir = TEST_PROJECT / ".lance-empty"
        try:
            # Create a minimal vault structure so VaultStore can connect
            store = VaultStore(lance_dir)
            store.ensure_table()

            model = EmbeddingModel()
            query_vec = model.encode_query("anything")

            results = store.hybrid_search(
                query_vector=query_vec,
                query_text="anything",
                limit=5,
            )
            assert results == []
        finally:
            if lance_dir.exists():
                shutil.rmtree(lance_dir, ignore_errors=True)

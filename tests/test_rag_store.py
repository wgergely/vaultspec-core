"""Tests for VaultStore: CRUD, hybrid search, and store helper edge cases."""

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


# ---- Store helper edge cases ----


class TestStoreHelpers:
    """Tests for store utility functions and edge cases."""

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

    def test_build_where_escapes_quotes(self):
        """_build_where should escape single quotes in filter values."""
        from rag.store import VaultStore

        result = VaultStore._build_where({"doc_type": "adr' OR 1=1 --"})
        assert result is not None
        # The single quote should be escaped (doubled)
        assert "''" in result
        # The unescaped injection should not be present
        assert "adr' OR" not in result

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

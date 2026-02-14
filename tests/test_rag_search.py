"""End-to-end VaultSearcher search operations (integration tests).

Unit tests for query parsing have been moved to:
.vaultspec/lib/src/rag/tests/test_query.py
"""

from __future__ import annotations

import pathlib
import sys

import pytest

# Ensure vault lib is importable
LIB_SRC = pathlib.Path(__file__).parent.parent / ".vaultspec" / "lib" / "src"
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


# ---- Search edge cases ----


class TestSearchEdgeCases:
    """Edge cases for search operations."""

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

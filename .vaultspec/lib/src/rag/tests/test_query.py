"""Unit tests for query parsing (extracted from test_rag_search.py)."""

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

pytestmark = pytest.mark.skipif(not HAS_RAG, reason="RAG dependencies not installed")


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

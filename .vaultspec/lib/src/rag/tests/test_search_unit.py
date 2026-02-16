"""Unit tests for rag.search — query parsing and data classes (no GPU)."""

import pytest
from rag.search import ParsedQuery, SearchResult, parse_query

pytestmark = [pytest.mark.unit]


class TestParsedQuery:
    def test_creation(self):
        pq = ParsedQuery(text="hello", filters={"doc_type": "adr"})
        assert pq.text == "hello"
        assert pq.filters == {"doc_type": "adr"}


class TestSearchResult:
    def test_creation(self):
        sr = SearchResult(
            id="test-doc",
            path="adr/test-doc.md",
            title="Test Doc",
            doc_type="adr",
            feature="auth",
            date="2026-02-08",
            score=0.95,
            snippet="Test content...",
        )
        assert sr.id == "test-doc"
        assert sr.score == 0.95


class TestParseQuery:
    def test_plain_text(self):
        result = parse_query("vector database")
        assert result.text == "vector database"
        assert result.filters == {}

    def test_type_filter(self):
        result = parse_query("type:adr vector database")
        assert result.text == "vector database"
        assert result.filters == {"doc_type": "adr"}

    def test_feature_filter(self):
        result = parse_query("feature:rag search stuff")
        assert result.text == "search stuff"
        assert result.filters == {"feature": "rag"}

    def test_date_filter(self):
        result = parse_query("date:2026-02 recent docs")
        assert result.text == "recent docs"
        assert result.filters == {"date": "2026-02"}

    def test_tag_filter(self):
        result = parse_query("tag:#research my query")
        assert result.text == "my query"
        assert result.filters == {"tag": "research"}

    def test_multiple_filters(self):
        result = parse_query("type:adr feature:auth authentication")
        assert result.text == "authentication"
        assert result.filters["doc_type"] == "adr"
        assert result.filters["feature"] == "auth"

    def test_only_filters_no_text(self):
        result = parse_query("type:adr feature:auth")
        assert result.text == ""
        assert len(result.filters) == 2

    def test_empty_query(self):
        result = parse_query("")
        assert result.text == ""
        assert result.filters == {}

    def test_tag_strips_hash(self):
        result = parse_query("tag:#deep-learning stuff")
        assert result.filters["tag"] == "deep-learning"

    def test_collapses_multiple_spaces(self):
        result = parse_query("type:adr  hello   world")
        assert result.text == "hello world"

    def test_unknown_prefix_not_extracted(self):
        result = parse_query("unknown:value hello")
        assert result.text == "unknown:value hello"
        assert result.filters == {}

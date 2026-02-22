"""Unit tests for VaultStore helper functions.

Extracted from tests/test_rag_store.py.
"""

from __future__ import annotations

import importlib.util

import pytest

HAS_RAG = all(
    importlib.util.find_spec(pkg) is not None
    for pkg in ("lancedb", "sentence_transformers", "torch")
)

pytestmark = [
    pytest.mark.unit,
    pytest.mark.skipif(not HAS_RAG, reason="RAG dependencies not installed"),
]


class TestStoreHelpers:
    """Tests for store utility functions and edge cases."""

    def test_parse_json_list_valid_json(self):
        """_parse_json_list should parse valid JSON arrays."""
        from ..store import _parse_json_list

        assert _parse_json_list('["#adr", "#editor"]') == ["#adr", "#editor"]
        assert _parse_json_list("[]") == []

    def test_parse_json_list_empty_string(self):
        """_parse_json_list should handle empty string gracefully."""
        from ..store import _parse_json_list

        assert _parse_json_list("") == []

    def test_parse_json_list_comma_separated_fallback(self):
        """_parse_json_list should fall back to comma-splitting for non-JSON."""
        from ..store import _parse_json_list

        result = _parse_json_list("#adr, #editor")
        assert result == ["#adr", "#editor"]

    def test_parse_json_list_non_array_json(self):
        """_parse_json_list with valid JSON that is not an array should
        fall back to comma splitting."""
        from ..store import _parse_json_list

        result = _parse_json_list('"just a string"')
        assert isinstance(result, list)

    def test_build_where_escapes_quotes(self):
        """_build_where should escape single quotes in filter values."""
        from .. import VaultStore

        result = VaultStore._build_where({"doc_type": "adr' OR 1=1 --"})
        assert result is not None
        # The single quote should be escaped (doubled)
        assert "''" in result
        # The unescaped injection should not be present
        assert "adr' OR" not in result

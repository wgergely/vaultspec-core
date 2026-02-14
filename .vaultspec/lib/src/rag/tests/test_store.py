"""Unit tests for VaultStore helper functions.

Extracted from tests/test_rag_store.py.
"""

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
    pytest.mark.unit,
    pytest.mark.skipif(not HAS_RAG, reason="RAG dependencies not installed"),
]


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

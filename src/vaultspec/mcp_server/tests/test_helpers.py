"""Unit tests for subagent server helper functions.

Extracted from the original dispatch server tests.
"""

from __future__ import annotations

import pytest

from ..subagent_tools import (
    _extract_artifacts,
    _merge_artifacts,
    _resolve_effective_mode,
    _strip_quotes,
)

pytestmark = [pytest.mark.unit]


class TestHelpers:
    def test_strip_quotes_normal(self):
        assert _strip_quotes('"hello"') == "hello"

    def test_strip_quotes_no_quotes(self):
        assert _strip_quotes("hello") == "hello"

    def test_strip_quotes_empty(self):
        assert _strip_quotes("") == ""

    def test_resolve_mode_explicit(self):
        assert _resolve_effective_mode("any", "read-only") == "read-only"

    def test_resolve_mode_default(self):
        # This test would normally look into _agent_cache,
        # but we are testing the logic flow here.
        assert _resolve_effective_mode("any", None) == "read-write"


class TestArtifactExtraction:
    def test_empty_text(self):
        assert _extract_artifacts("") == []

    def test_docs_paths(self):
        text = "I created .vault/plan/my-plan.md and .vault/adr/my-adr.md"
        result = _extract_artifacts(text)
        assert ".vault/adr/my-adr.md" in result
        assert ".vault/plan/my-plan.md" in result

    def test_src_paths(self):
        text = "Modified src/main.rs and src/lib.rs for the feature."
        result = _extract_artifacts(text)
        assert "src/main.rs" in result
        assert "src/lib.rs" in result

    def test_deduplication(self):
        text = "Modified src/main.rs then tested src/main.rs again."
        result = _extract_artifacts(text)
        assert result.count("src/main.rs") == 1

    def test_sorted_output(self):
        text = "Created src/z.rs then src/a.rs then .vault/b.md"
        result = _extract_artifacts(text)
        assert result == sorted(result)


class TestMergeArtifacts:
    def test_empty_both(self):
        assert _merge_artifacts([], []) == []

    def test_text_only(self):
        result = _merge_artifacts(["src/main.rs"], [])
        assert result == ["src/main.rs"]

    def test_written_only(self):
        result = _merge_artifacts([], [".vault/plan.md"])
        assert result == [".vault/plan.md"]

    def test_deduplication(self):
        result = _merge_artifacts(
            [".vault/plan.md", "src/main.rs"],
            [".vault/plan.md", "src/lib.rs"],
        )
        assert result.count(".vault/plan.md") == 1
        assert "src/main.rs" in result
        assert "src/lib.rs" in result

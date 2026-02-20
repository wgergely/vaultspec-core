"""Robustness tests: document edge cases, parser handling, graph re-ranking."""

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
    pytest.mark.search,
    pytest.mark.skipif(not HAS_RAG, reason="RAG dependencies not installed"),
]


# ---- Robustness Tests ----


class TestRobustness:
    """Edge-case and robustness tests for the RAG pipeline.

    Covers documents without frontmatter, non-standard metadata schemas,
    unicode content, and graph re-ranking with orphan documents.
    """

    # -- Document edge cases --

    def test_stories_without_frontmatter_skipped(self, rag_components):
        """Stories in .vault/stories/ have no YAML frontmatter and are French fiction.

        Since DocType enum doesn't include 'stories', get_doc_type returns None
        and prepare_document returns None. Verify they are gracefully skipped.
        """
        from rag.indexer import prepare_document
        from vaultcore.scanner import scan_vault

        root = rag_components["root"]
        story_paths = [p for p in scan_vault(root) if "stories" in p.parts]
        assert len(story_paths) > 0, "Should find story files in scanner output"

        for path in story_paths:
            doc = prepare_document(path, root)
            assert doc is None, (
                f"Story {path.name} should be skipped (no valid DocType), "
                f"but prepare_document returned a doc"
            )

    def test_audit_nonstandard_frontmatter_indexed(self, rag_components):
        """audit/2026-02-07-main-window-safety-audit.md has 'feature:' key
        instead of 'tags:' array. DocType.AUDIT exists, so get_doc_type
        returns AUDIT and the doc is indexed despite nonstandard frontmatter.
        """
        from rag.indexer import prepare_document
        from vaultcore.scanner import scan_vault

        root = rag_components["root"]
        audit_paths = [p for p in scan_vault(root) if "audit" in p.parts]
        assert len(audit_paths) > 0, "Should find audit files in scanner output"

        for path in audit_paths:
            doc = prepare_document(path, root)
            assert doc is not None, (
                f"Audit doc {path.name} should be indexed (DocType.AUDIT is valid)"
            )
            assert doc.doc_type == "audit"

    def test_unicode_content_in_parser(self):
        """French stories have accented chars. Verify parse_vault_metadata
        handles unicode content without crashing.
        """
        from vaultcore.parser import parse_vault_metadata

        # Simulate content with accented French characters
        french_content = (
            "# Chapitre 1 : La M\u00e9lancolie de Croustillant\n\n"
            "Au c\u0153ur d'une boulangerie parisienne, o\u00f9 les "
            "effluves de beurre et de sucre flottaient."
        )
        metadata, body = parse_vault_metadata(french_content)
        # No frontmatter, so metadata is empty
        assert metadata.tags == []
        assert metadata.date is None
        assert "M\u00e9lancolie" in body

    def test_feature_key_frontmatter_parsed(self):
        """Documents using 'feature:' key (Pattern B) instead of 'tags:' array
        should not crash the parser. The feature value is stored differently.
        """
        from vaultcore.parser import parse_vault_metadata

        content = (
            "---\n"
            "feature: dispatch\n"
            "date: 2026-02-07\n"
            "related:\n"
            '  - "[[some-doc]]"\n'
            "---\n"
            "# Test Document\n"
        )
        metadata, body = parse_vault_metadata(content)
        # Parser doesn't crash. 'feature' is not in metadata.tags (which is
        # only populated from 'tags:' key), but date and related are parsed.
        assert metadata.date == "2026-02-07"
        assert len(metadata.related) >= 1
        assert "# Test Document" in body

    def test_content_with_embedded_yaml_separators(self):
        """Documents with --- inside content (not frontmatter) should parse
        correctly. The regex anchors to ^--- so internal --- is not confused.
        """
        from vaultcore.parser import parse_vault_metadata

        content = (
            "# Some Research Doc\n\n"
            "Some content here.\n\n"
            "---\n\n"
            "## Section after separator\n\n"
            "More content."
        )
        metadata, body = parse_vault_metadata(content)
        # No frontmatter block, so metadata is empty defaults
        assert metadata.tags == []
        assert metadata.date is None
        # The full content including --- should be in body
        assert "---" in body

    def test_content_with_code_block_yaml_separators(self):
        """Documents with --- inside code blocks should not confuse the parser."""
        from vaultcore.parser import parse_vault_metadata

        content = (
            "---\n"
            'tags: ["#research", "#dispatch"]\n'
            "date: 2026-02-07\n"
            "---\n"
            "# Title\n\n"
            "```yaml\n"
            "---\n"
            "fake: frontmatter\n"
            "---\n"
            "```\n"
        )
        metadata, body = parse_vault_metadata(content)
        assert metadata.tags == ["#research", "#dispatch"]
        assert metadata.date == "2026-02-07"
        assert "fake: frontmatter" in body

    # -- Graph re-ranking edge cases --

    def test_graph_reranking_with_orphans(self, rag_components):
        """Orphaned docs (no in-links) should still appear in results.

        Graph re-ranking should boost well-connected docs but not
        eliminate orphans from results.
        """
        from rag.search import VaultSearcher

        model = rag_components["model"]
        store = rag_components["store"]
        root = rag_components["root"]

        searcher = VaultSearcher(root, model, store)
        # Use a broad query that should match many docs
        results = searcher.search("editor implementation", top_k=15)

        assert len(results) > 0, "Should find results for broad query"
        # All results should have valid scores (even orphans)
        for r in results:
            assert r.score > 0, f"Result {r.id} has non-positive score: {r.score}"

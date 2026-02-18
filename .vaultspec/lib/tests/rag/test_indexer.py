"""Tests for VaultIndexer: full/incremental indexing and document preparation."""

from __future__ import annotations

import pytest
from tests.constants import TEST_PROJECT

# Check if RAG deps are available
try:
    import lancedb  # noqa: F401
    import sentence_transformers  # noqa: F401
    import torch  # noqa: F401

    HAS_RAG = True
except ImportError:
    HAS_RAG = False

pytestmark = [
    pytest.mark.index,
    pytest.mark.skipif(not HAS_RAG, reason="RAG dependencies not installed"),
]

# ---- Indexer Tests ----


class TestVaultIndexer:
    """Tests for the indexing pipeline with real vault data."""

    @pytest.mark.index
    @pytest.mark.timeout(60)
    def test_full_index_counts(self, rag_components):
        result = rag_components["index_result"]
        assert result.total > 0
        assert result.added > 0
        assert result.duration_ms >= 0
        assert result.device == "cuda"

    @pytest.mark.index
    @pytest.mark.timeout(60)
    def test_index_matches_store_count(self, rag_components):
        result = rag_components["index_result"]
        store = rag_components["store"]
        assert result.total == store.count()

    @pytest.mark.quality
    @pytest.mark.timeout(300)
    def test_incremental_index_no_changes(self, rag_components_full):
        """Incremental index with no changes should report zero additions.

        Requires full corpus because incremental_index() scans the full
        vault and compares against stored ids.
        """
        indexer = rag_components_full["indexer"]
        result = indexer.incremental_index()
        # No new files, no modifications, no deletions
        assert result.added == 0
        assert result.removed == 0
        # Total should match the full index
        assert result.total == rag_components_full["index_result"].total


# ---- Document Preparation Tests ----


class TestDocumentPreparation:
    """Tests for individual document preparation."""

    @pytest.mark.index
    @pytest.mark.timeout(60)
    def test_prepare_real_document(self):
        from rag.indexer import prepare_document

        # Find a real document in the test-project
        from vault.scanner import scan_vault

        docs = list(scan_vault(TEST_PROJECT))
        assert len(docs) > 0, "test-project should have documents"

        doc = prepare_document(docs[0], TEST_PROJECT)
        assert doc is not None
        assert doc.id
        assert doc.path
        assert doc.doc_type in ("adr", "audit", "exec", "plan", "reference", "research")
        assert doc.content

    @pytest.mark.quality
    @pytest.mark.timeout(300)
    def test_prepare_all_documents(self):
        from rag.indexer import prepare_document
        from vault.scanner import scan_vault

        prepared = 0
        skipped = 0
        for path in scan_vault(TEST_PROJECT):
            doc = prepare_document(path, TEST_PROJECT)
            if doc is not None:
                prepared += 1
                assert doc.id == path.stem
            else:
                skipped += 1

        assert prepared > 0, "Should prepare at least some documents"


# ---- Index edge cases ----


class TestIndexEdgeCases:
    """Edge cases for indexing operations."""

    @pytest.mark.quality
    @pytest.mark.timeout(300)
    def test_double_full_index_idempotent(self, rag_components_full):
        """Two full_index() calls should yield the same document count."""
        indexer = rag_components_full["indexer"]
        store = rag_components_full["store"]

        first_count = store.count()

        # Run full index again
        result = indexer.full_index()
        second_count = store.count()

        assert first_count == second_count, (
            f"Full index should be idempotent: {first_count} vs {second_count}"
        )
        assert result.total == second_count

    @pytest.mark.quality
    @pytest.mark.timeout(300)
    def test_incremental_after_full_stable(self, rag_components_full):
        """Incremental index after full should report zero changes."""
        indexer = rag_components_full["indexer"]
        result = indexer.incremental_index()

        assert result.added == 0, f"Expected 0 added, got {result.added}"
        assert result.removed == 0, f"Expected 0 removed, got {result.removed}"
        assert result.total == rag_components_full["index_result"].total

    @pytest.mark.quality
    @pytest.mark.timeout(300)
    def test_docs_without_frontmatter_counted(self):
        """Verify how many docs in the vault lack frontmatter entirely.
        These should all be in unsupported directories (stories) or have
        no YAML block at all (some research docs).
        """
        from vault.parser import parse_vault_metadata
        from vault.scanner import scan_vault

        no_frontmatter = []
        for path in scan_vault(TEST_PROJECT):
            content = path.read_text(encoding="utf-8")
            metadata, _body = parse_vault_metadata(content)
            if not metadata.tags and metadata.date is None:
                no_frontmatter.append(path.name)

        # We expect some docs without frontmatter (stories, some research)
        assert len(no_frontmatter) > 0, "Should find docs without frontmatter"

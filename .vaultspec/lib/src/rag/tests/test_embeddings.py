"""Tests for embedding model: EmbeddingModel and DeviceInfo."""

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


# ---- Embedding Model Tests ----


class TestEmbeddingModel:
    """Tests for the real EmbeddingModel with nomic-embed-text-v1.5."""

    def test_model_loads(self, rag_components):
        model = rag_components["model"]
        assert model.device == "cuda"

    def test_encode_documents_shape(self, rag_components):
        model = rag_components["model"]
        texts = ["This is a test document about architecture decisions."]
        vectors = model.encode_documents(texts)
        assert vectors.shape[0] == 1
        assert vectors.shape[1] == model.dimension

    def test_encode_query_shape(self, rag_components):
        model = rag_components["model"]
        vector = model.encode_query("vector database")
        assert vector.shape == (model.dimension,)

    def test_document_query_similarity(self, rag_components):
        """Documents about a topic should be more similar to related queries."""
        import numpy as np

        model = rag_components["model"]

        doc_vec = model.encode_documents(
            ["LanceDB is an embedded vector database for semantic search"]
        )[0]
        related_query = model.encode_query("vector database for search")
        unrelated_query = model.encode_query("chocolate cake recipe")

        sim_related = float(np.dot(doc_vec, related_query))
        sim_unrelated = float(np.dot(doc_vec, unrelated_query))

        assert sim_related > sim_unrelated

    def test_encode_documents_batched(self, rag_components):
        """Batched encoding with batch_size=2 on 3 docs should produce
        the same shape as unbatched encoding.
        """
        model = rag_components["model"]
        texts = [
            "First document about architecture.",
            "Second document about testing.",
            "Third document about performance.",
        ]
        vectors = model.encode_documents(texts, batch_size=2)
        assert vectors.shape[0] == 3
        assert vectors.shape[1] == model.dimension

    def test_query_embedding_cache_hit(self, rag_components):
        """Repeated identical queries should hit the LRU cache."""
        model = rag_components["model"]
        query = "cache test query for embedding"

        # Clear any previous cache state
        model._encode_query_cached.cache_clear()

        model.encode_query(query)
        info_after_first = model._encode_query_cached.cache_info()
        assert info_after_first.misses >= 1

        model.encode_query(query)
        info_after_second = model._encode_query_cached.cache_info()
        assert info_after_second.hits >= 1


# ---- Device Info Tests ----


class TestDeviceInfo:
    """Tests for device detection utility."""

    def test_get_device_info(self):
        from rag.embeddings import get_device_info

        info = get_device_info()
        assert info["device"] == "cuda"
        assert info["gpu_name"] is not None
        assert info["vram_mb"] is not None

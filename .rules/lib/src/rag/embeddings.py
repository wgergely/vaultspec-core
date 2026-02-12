"""Embedding model wrapper for vault semantic search.

Uses nomic-embed-text-v1.5 via sentence-transformers. All heavy imports
are guarded so that core vault tools work without RAG dependencies.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np

logger = logging.getLogger(__name__)


def _check_rag_deps() -> None:
    """Verify RAG dependencies are installed."""
    try:
        import sentence_transformers  # noqa: F401
        import torch  # noqa: F401
    except ImportError:
        raise ImportError(
            "RAG dependencies not installed. Run: pip install -e '.[rag]'"
        ) from None


def get_device_info() -> dict:
    """Return device information for embedding inference.

    Returns dict with keys: device, gpu_name, vram_mb.
    """
    _check_rag_deps()
    import torch

    if torch.cuda.is_available():
        gpu_name = torch.cuda.get_device_name(0)
        vram_mb = torch.cuda.get_device_properties(0).total_mem // (1024 * 1024)
        return {"device": "cuda", "gpu_name": gpu_name, "vram_mb": vram_mb}
    return {"device": "cpu", "gpu_name": None, "vram_mb": None}


class EmbeddingModel:
    """Wrapper around nomic-embed-text-v1.5 for vault document embeddings."""

    MODEL_NAME = "nomic-ai/nomic-embed-text-v1.5"
    DIMENSION = 768
    DOCUMENT_PREFIX = "search_document: "
    QUERY_PREFIX = "search_query: "

    def __init__(self, device: str | None = None) -> None:
        _check_rag_deps()
        import torch
        from sentence_transformers import SentenceTransformer

        if device is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"

        self._device = device
        self.model = SentenceTransformer(
            self.MODEL_NAME, device=device, trust_remote_code=True
        )
        logger.info("Embedding model loaded on %s", device)

    @property
    def device(self) -> str:
        """Return the current device string."""
        return self._device

    def encode_documents(self, texts: list[str]) -> np.ndarray:
        """Encode document texts with the document prefix.

        Args:
            texts: List of document texts (title + body).

        Returns:
            numpy array of shape (n, 768) with normalized embeddings.
        """
        import numpy as np

        prefixed = [f"{self.DOCUMENT_PREFIX}{t}" for t in texts]
        result = self.model.encode(
            prefixed, show_progress_bar=True, normalize_embeddings=True
        )
        return np.asarray(result)

    def encode_query(self, query: str) -> np.ndarray:
        """Encode a search query with the query prefix.

        Args:
            query: Natural language query string.

        Returns:
            numpy array of shape (768,) with normalized embedding.
        """
        import numpy as np

        prefixed = f"{self.QUERY_PREFIX}{query}"
        result = self.model.encode(
            prefixed, show_progress_bar=False, normalize_embeddings=True
        )
        return np.asarray(result)

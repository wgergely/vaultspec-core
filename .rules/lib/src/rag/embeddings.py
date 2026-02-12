"""Embedding model wrapper for vault semantic search.

Uses nomic-embed-text-v1.5 via sentence-transformers. All heavy imports
are guarded so that core vault tools work without RAG dependencies.
"""

from __future__ import annotations

import functools
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
    DEFAULT_BATCH_SIZE = 64

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

    def encode_documents(
        self, texts: list[str], *, batch_size: int | None = None
    ) -> np.ndarray:
        """Encode document texts with the document prefix.

        Args:
            texts: List of document texts (title + body).
            batch_size: Max texts per encoding batch. Defaults to
                ``DEFAULT_BATCH_SIZE``.

        Returns:
            numpy array of shape (n, 768) with normalized embeddings.
        """
        import numpy as np

        if batch_size is None:
            batch_size = self.DEFAULT_BATCH_SIZE

        prefixed = [f"{self.DOCUMENT_PREFIX}{t}" for t in texts]

        if len(prefixed) <= batch_size:
            result = np.asarray(
                self.model.encode(
                    prefixed, show_progress_bar=True, normalize_embeddings=True
                )
            )
        else:
            all_embeddings = []
            for start in range(0, len(prefixed), batch_size):
                chunk = prefixed[start : start + batch_size]
                batch_result = self.model.encode(
                    chunk, show_progress_bar=True, normalize_embeddings=True
                )
                all_embeddings.append(np.asarray(batch_result))
            result = np.concatenate(all_embeddings, axis=0)

        # Release GPU memory after large batch encoding
        if self._device == "cuda":
            try:
                import torch

                torch.cuda.empty_cache()
            except Exception:
                pass

        return result

    def encode_query(self, query: str) -> np.ndarray:
        """Encode a search query with the query prefix.

        Results are cached (LRU, 128 entries) to avoid re-encoding
        identical queries.

        Args:
            query: Natural language query string.

        Returns:
            numpy array of shape (768,) with normalized embedding.
        """
        import numpy as np

        cached_tuple = self._encode_query_cached(query)
        return np.asarray(cached_tuple, dtype=np.float32)

    @functools.lru_cache(maxsize=128)  # noqa: B019
    def _encode_query_cached(self, query: str) -> tuple[float, ...]:
        """Encode and cache query as a tuple (hashable for LRU cache)."""
        prefixed = f"{self.QUERY_PREFIX}{query}"
        result = self.model.encode(
            prefixed, show_progress_bar=False, normalize_embeddings=True
        )
        return tuple(float(x) for x in result)

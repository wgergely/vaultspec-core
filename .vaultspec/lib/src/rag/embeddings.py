"""Embedding model wrapper for vault semantic search.

Uses nomic-embed-text-v1.5 via sentence-transformers on CUDA GPU.
CPU is NOT supported — all operations require a CUDA-enabled GPU.
"""

from __future__ import annotations

import functools
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np

logger = logging.getLogger(__name__)


class GPUNotAvailableError(RuntimeError):
    """Raised when CUDA GPU is required but not available."""

    pass


def _check_rag_deps() -> None:
    """Verify RAG dependencies are installed."""
    try:
        import sentence_transformers  # noqa: F401
        import torch  # noqa: F401
    except ImportError:
        raise ImportError(
            "RAG dependencies not installed. Run: pip install -e '.[rag]'"
        ) from None


def _require_cuda() -> None:
    """Verify CUDA GPU is available. Fails fast if not.

    Raises:
        GPUNotAvailableError: If no CUDA device is detected. This is a
            fatal error — CPU fallback is not supported.
    """
    import torch

    if not torch.cuda.is_available():
        cuda_version = torch.version.cuda
        torch_version = torch.__version__
        raise GPUNotAvailableError(
            f"CUDA GPU required but not available. "
            f"Torch version: {torch_version}, CUDA compiled: {cuda_version}. "
            f"If you have an NVIDIA GPU, install CUDA-enabled PyTorch: "
            f"pip install torch --index-url https://download.pytorch.org/whl/cu124"
        )


def get_device_info() -> dict:
    """Return GPU device information for embedding inference.

    Returns:
        Dict with keys: device, gpu_name, vram_mb.

    Raises:
        GPUNotAvailableError: If no CUDA device is detected.
    """
    _check_rag_deps()
    _require_cuda()
    import torch

    gpu_name = torch.cuda.get_device_name(0)
    props = torch.cuda.get_device_properties(0)
    # PyTorch 2.10+ uses total_memory, older versions use total_mem
    try:
        total_bytes = props.total_memory
    except AttributeError:
        total_bytes = props.total_mem
    vram_mb = total_bytes // (1024 * 1024)
    return {
        "device": "cuda",
        "gpu_name": gpu_name,
        "vram_mb": vram_mb,
    }


class EmbeddingModel:
    """Wrapper around nomic-embed-text-v1.5 for vault document embeddings.

    Requires a CUDA-enabled GPU. Will fail fast on initialization if
    no GPU is available.
    """

    MODEL_NAME = "nomic-ai/nomic-embed-text-v1.5"
    DIMENSION = 768
    DOCUMENT_PREFIX = "search_document: "
    QUERY_PREFIX = "search_query: "

    @staticmethod
    def _default_batch_size() -> int:
        from core.config import get_config

        return get_config().embedding_batch_size

    @staticmethod
    def _default_max_embed_chars() -> int:
        from core.config import get_config

        return get_config().max_embed_chars

    # Class-level constants for backwards compat with direct attribute access
    DEFAULT_BATCH_SIZE = 64
    MAX_EMBED_CHARS = 8000

    def __init__(self) -> None:
        _check_rag_deps()
        _require_cuda()
        from core.config import get_config
        from sentence_transformers import SentenceTransformer

        model_name = get_config().embedding_model
        self._device = "cuda"
        self.model = SentenceTransformer(
            model_name, device="cuda", trust_remote_code=True
        )
        logger.info("Embedding model loaded on cuda")

    @property
    def device(self) -> str:
        """Return the current device string (always 'cuda')."""
        return self._device

    def encode_documents(
        self, texts: list[str], *, batch_size: int | None = None
    ) -> np.ndarray:
        """Encode document texts with the document prefix.

        Sorts texts by length before batching to minimize padding waste.
        Long documents are truncated by the tokenizer at 8192 tokens.

        Args:
            texts: List of document texts (title + body).
            batch_size: Max texts per encoding batch. Defaults to
                ``DEFAULT_BATCH_SIZE``.

        Returns:
            numpy array of shape (n, 768) with normalized embeddings,
            in the same order as the input texts.
        """
        import numpy as np

        if batch_size is None:
            batch_size = self._default_batch_size()

        # Truncate long documents to avoid massive padding overhead.
        # Full text is still in LanceDB for BM25; embedding captures key concepts.
        max_chars = self._default_max_embed_chars()
        truncated = [t[:max_chars] for t in texts]
        prefixed = [f"{self.DOCUMENT_PREFIX}{t}" for t in truncated]

        # Sort by length to group similar-sized docs together,
        # minimizing padding waste in GPU batches.
        indexed = sorted(enumerate(prefixed), key=lambda x: len(x[1]))
        sorted_texts = [t for _, t in indexed]
        original_indices = [i for i, _ in indexed]

        # Encode in length-sorted batches
        all_embeddings: list[np.ndarray] = []
        for start in range(0, len(sorted_texts), batch_size):
            chunk = sorted_texts[start : start + batch_size]
            batch_result = self.model.encode(
                chunk, show_progress_bar=True, normalize_embeddings=True
            )
            all_embeddings.append(np.asarray(batch_result))

        sorted_result = np.concatenate(all_embeddings, axis=0)

        # Restore original order
        result = np.empty_like(sorted_result)
        for sorted_idx, orig_idx in enumerate(original_indices):
            result[orig_idx] = sorted_result[sorted_idx]

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

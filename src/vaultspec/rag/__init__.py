"""RAG (Retrieval-Augmented Generation) for vault documents.

All public symbols are lazily loaded to avoid importing heavy ML
dependencies (torch, sentence-transformers, lancedb) at package
import time.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .api import VaultRAG as VaultRAG
    from .api import get_document as get_document
    from .api import get_engine as get_engine
    from .api import get_related as get_related
    from .api import get_status as get_status
    from .api import index as index
    from .api import list_documents as list_documents
    from .api import reset_engine as reset_engine
    from .api import search as search
    from .embeddings import CUDA_INDEX_TAG as CUDA_INDEX_TAG
    from .embeddings import CUDA_INDEX_URL as CUDA_INDEX_URL
    from .embeddings import EmbeddingModel as EmbeddingModel
    from .embeddings import GPUNotAvailableError as GPUNotAvailableError
    from .embeddings import get_device_info as get_device_info
    from .indexer import IndexResult as IndexResult
    from .indexer import VaultIndexer as VaultIndexer
    from .indexer import prepare_document as prepare_document
    from .search import ParsedQuery as ParsedQuery
    from .search import SearchResult as SearchResult
    from .search import VaultSearcher as VaultSearcher
    from .search import parse_query as parse_query
    from .search import rerank_with_graph as rerank_with_graph
    from .store import EMBEDDING_DIM as EMBEDDING_DIM
    from .store import VaultDocument as VaultDocument
    from .store import VaultStore as VaultStore

_MODULE_MAP: dict[str, str] = {
    "VaultRAG": "api",
    "get_engine": "api",
    "reset_engine": "api",
    "list_documents": "api",
    "get_document": "api",
    "get_related": "api",
    "get_status": "api",
    "index": "api",
    "search": "api",
    "CUDA_INDEX_TAG": "embeddings",
    "CUDA_INDEX_URL": "embeddings",
    "GPUNotAvailableError": "embeddings",
    "EmbeddingModel": "embeddings",
    "get_device_info": "embeddings",
    "IndexResult": "indexer",
    "VaultIndexer": "indexer",
    "prepare_document": "indexer",
    "ParsedQuery": "search",
    "SearchResult": "search",
    "VaultSearcher": "search",
    "parse_query": "search",
    "rerank_with_graph": "search",
    "EMBEDDING_DIM": "store",
    "VaultDocument": "store",
    "VaultStore": "store",
}


def __getattr__(name: str) -> object:
    """Lazily import a public symbol from its sub-module on first access.

    Args:
        name: Attribute name being looked up on this package.

    Returns:
        The requested symbol imported from its sub-module.

    Raises:
        AttributeError: If ``name`` is not a known public symbol.
    """
    if name in _MODULE_MAP:
        import importlib

        module = importlib.import_module(f".{_MODULE_MAP[name]}", __name__)
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

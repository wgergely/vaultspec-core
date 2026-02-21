"""RAG (Retrieval-Augmented Generation) for vault documents.

All public symbols are lazily loaded to avoid importing heavy ML
dependencies (torch, sentence-transformers, lancedb) at package
import time.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .api import (
        VaultRAG,
        get_document,
        get_engine,
        get_related,
        get_status,
        index,
        list_documents,
        reset_engine,
        search,
    )
    from .embeddings import (
        CUDA_INDEX_TAG,
        CUDA_INDEX_URL,
        EmbeddingModel,
        GPUNotAvailableError,
        get_device_info,
    )
    from .indexer import IndexResult, VaultIndexer, prepare_document
    from .search import (
        ParsedQuery,
        SearchResult,
        VaultSearcher,
        parse_query,
        rerank_with_graph,
    )
    from .store import EMBEDDING_DIM, VaultDocument, VaultStore

__all__ = [
    # embeddings
    "CUDA_INDEX_TAG",
    "CUDA_INDEX_URL",
    # store
    "EMBEDDING_DIM",
    "EmbeddingModel",
    "GPUNotAvailableError",
    # indexer
    "IndexResult",
    # search
    "ParsedQuery",
    "SearchResult",
    "VaultDocument",
    "VaultIndexer",
    # api
    "VaultRAG",
    "VaultSearcher",
    "VaultStore",
    "get_device_info",
    "get_document",
    "get_engine",
    "get_related",
    "get_status",
    "index",
    "list_documents",
    "parse_query",
    "prepare_document",
    "rerank_with_graph",
    "reset_engine",
    "search",
]

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
    if name in _MODULE_MAP:
        import importlib

        module = importlib.import_module(f".{_MODULE_MAP[name]}", __name__)
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

"""Public API facade for the vault RAG system.

Backs both the CLI and future MCP server.  Tier 1 functions work with
just the vault filesystem (no RAG deps).  Tier 2 functions require
torch, sentence-transformers, and lancedb.
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pathlib

    from .embeddings import EmbeddingModel
    from .indexer import IndexResult, VaultIndexer
    from .search import SearchResult, VaultSearcher
    from .store import VaultStore

logger = logging.getLogger(__name__)

__all__ = [
    "VaultRAG",
    "get_document",
    "get_engine",
    "get_related",
    "get_status",
    "index",
    "list_documents",
    "reset_engine",
    "search",
]


class VaultRAG:
    """Singleton engine that holds shared RAG resources.

    All heavy dependencies (torch, sentence-transformers, lancedb) are loaded
    lazily on first property access and protected by a threading lock for
    safe concurrent initialization.

    Attributes:
        root_dir: Workspace root directory used to locate the vector store and
            vault documents.
    """

    def __init__(self, root_dir: pathlib.Path) -> None:
        """Initialize the engine without loading any ML dependencies.

        Args:
            root_dir: Workspace root directory.
        """
        self.root_dir = root_dir
        self._lock = threading.Lock()
        self._model = None
        self._store = None
        self._indexer = None
        self._searcher = None

    # -- lazy properties (thread-safe via self._lock) ------------------------

    @property
    def model(self) -> EmbeddingModel:
        """Return the shared embedding model, initializing it on first access.

        Returns:
            The shared :class:`~.embeddings.EmbeddingModel` instance.
        """
        if self._model is None:
            with self._lock:
                if self._model is None:
                    from .embeddings import (
                        EmbeddingModel as _EmbeddingModel,
                    )

                    self._model = _EmbeddingModel()
        assert self._model is not None  # guaranteed by double-check init
        return self._model

    @property
    def store(self) -> VaultStore:
        """Return the shared vector store, initializing it on first access.

        Returns:
            The shared :class:`~.store.VaultStore` instance.
        """
        if self._store is None:
            with self._lock:
                if self._store is None:
                    from .store import VaultStore as _VaultStore

                    self._store = _VaultStore(self.root_dir)
        assert self._store is not None  # guaranteed by double-check init
        return self._store

    @property
    def indexer(self) -> VaultIndexer:
        """Return the shared indexer, initializing it on first access.

        Returns:
            The shared :class:`~.indexer.VaultIndexer` instance.
        """
        if self._indexer is None:
            with self._lock:
                if self._indexer is None:
                    from .indexer import VaultIndexer as _VaultIndexer

                    self._indexer = _VaultIndexer(self.root_dir, self.model, self.store)
        assert self._indexer is not None  # guaranteed by double-check init
        return self._indexer

    @property
    def searcher(self) -> VaultSearcher:
        """Return the shared searcher, initializing it on first access.

        Returns:
            The shared :class:`~.search.VaultSearcher` instance.
        """
        if self._searcher is None:
            with self._lock:
                if self._searcher is None:
                    from .search import VaultSearcher as _VaultSearcher

                    self._searcher = _VaultSearcher(
                        self.root_dir, self.model, self.store
                    )
        assert self._searcher is not None  # guaranteed by double-check init
        return self._searcher

    def close(self) -> None:
        """Release resources held by the engine."""
        if self._store is not None:
            self._store.close()
        self._model = None
        self._store = None
        self._indexer = None
        self._searcher = None


_engine: VaultRAG | None = None
_engine_lock = threading.Lock()


def reset_engine() -> None:
    """Release resources and clear the module-level singleton."""
    global _engine
    with _engine_lock:
        if _engine is not None:
            _engine.close()
        _engine = None


def get_engine(root_dir: pathlib.Path) -> VaultRAG:
    """Return the module-level VaultRAG singleton, creating it if needed.

    Args:
        root_dir: Workspace root directory. If the existing singleton was
            created for a different directory it is closed and recreated.

    Returns:
        The active :class:`VaultRAG` singleton for ``root_dir``.

    Raises:
        ImportError: If RAG is disabled by configuration.
        GPUNotAvailableError: If no CUDA device is detected. CPU is not
            supported — all Tier 2 operations require a CUDA-enabled GPU.
    """
    global _engine
    if _engine is None or _engine.root_dir != root_dir:
        with _engine_lock:
            # Double-check under lock
            if _engine is None or _engine.root_dir != root_dir:
                if _engine is not None:
                    _engine.close()
                _engine = VaultRAG(root_dir)

                # Fail fast if RAG is disabled by configuration
                from ..config import get_config

                if not get_config().rag_enabled:
                    _engine = None
                    raise ImportError(
                        "RAG disabled by configuration (VAULTSPEC_RAG_ENABLED=false)"
                    )

                # Fail fast if GPU is unavailable
                try:
                    from .embeddings import _require_cuda

                    _require_cuda()
                except ImportError:
                    pass
                except Exception:
                    _engine = None
                    raise

    assert _engine is not None  # guaranteed by init block above
    return _engine


def list_documents(
    root_dir: pathlib.Path,
    *,
    doc_type: str | None = None,
    feature: str | None = None,
) -> list[dict]:
    """List vault documents with optional filtering by type or feature.

    Scans the vault filesystem directly — no GPU or vector store required.

    Args:
        root_dir: Workspace root directory.
        doc_type: If set, only return documents whose ``doc_type`` value
            matches this string (e.g. ``"plan"``, ``"adr"``).
        feature: If set, only return documents whose non-directory tag
            matches this feature name (e.g. ``"editor-demo"``).

    Returns:
        List of document dicts, each containing keys: ``id``, ``path``,
        ``title``, ``doc_type``, ``feature``, ``date``, ``tags``.
    """
    from ..vaultcore import (
        DocType,
        get_doc_type,
        parse_vault_metadata,
        scan_vault,
    )

    docs: list[dict] = []
    for path in scan_vault(root_dir):
        dt = get_doc_type(path, root_dir)
        if dt is None:
            continue
        if doc_type and dt.value != doc_type:
            continue

        content = path.read_text(encoding="utf-8")
        metadata, body = parse_vault_metadata(content)

        feature_tag = ""
        for tag in metadata.tags:
            if not DocType.from_tag(tag):
                feature_tag = tag.lstrip("#")
        if feature and feature_tag != feature:
            continue

        title = ""
        for line in body.splitlines():
            if line.strip().startswith("# "):
                title = line.strip()[2:].strip()
                break
        if not title:
            title = path.stem

        from ..config import get_config

        docs_dir = root_dir / get_config().docs_dir
        try:
            rel_path = str(path.relative_to(docs_dir)).replace("\\", "/")
        except ValueError:
            rel_path = path.name

        docs.append(
            {
                "id": path.stem,
                "path": rel_path,
                "title": title,
                "doc_type": dt.value,
                "feature": feature_tag,
                "date": metadata.date or "",
                "tags": metadata.tags,
            }
        )
    return docs


def get_document(root_dir: pathlib.Path, doc_id: str) -> dict | None:
    """Retrieve a single document by ID, or ``None`` if not found.

    Tries the vector store first for speed, then falls back to a full vault
    filesystem scan when the vector store is unavailable or does not contain
    the document.

    Args:
        root_dir: Workspace root directory.
        doc_id: Stem of the document filename (without ``.md`` extension).

    Returns:
        Document dict with keys ``id``, ``path``, ``title``, ``doc_type``,
        ``feature``, ``date``, ``tags``, ``related``, and ``content``,
        or ``None`` if no matching document is found.
    """
    # Try the vector store first (fast, already parsed)
    try:
        from .embeddings import GPUNotAvailableError

        try:
            store = get_engine(root_dir).store
            result = store.get_by_id(doc_id)
            if result:
                return result
        except (ImportError, GPUNotAvailableError):
            logger.warning("RAG/GPU not available, falling back to filesystem")
    except (FileNotFoundError, OSError) as e:
        logger.warning("Vector store lookup failed: %s", e)

    # Fallback: scan the vault filesystem
    from ..vaultcore import (
        DocType,
        get_doc_type,
        parse_vault_metadata,
        scan_vault,
    )

    for path in scan_vault(root_dir):
        if path.stem == doc_id:
            dt = get_doc_type(path, root_dir)
            content = path.read_text(encoding="utf-8")
            metadata, body = parse_vault_metadata(content)

            feature_tag = ""
            for tag in metadata.tags:
                if not DocType.from_tag(tag):
                    feature_tag = tag.lstrip("#")

            title = ""
            for line in body.splitlines():
                if line.strip().startswith("# "):
                    title = line.strip()[2:].strip()
                    break
            if not title:
                title = path.stem

            from ..config import get_config

            docs_dir = root_dir / get_config().docs_dir
            try:
                rel_path = str(path.relative_to(docs_dir)).replace("\\", "/")
            except ValueError:
                rel_path = path.name

            return {
                "id": path.stem,
                "path": rel_path,
                "title": title,
                "doc_type": dt.value if dt else "",
                "feature": feature_tag,
                "date": metadata.date or "",
                "tags": metadata.tags,
                "related": metadata.related,
                "content": body.strip(),
            }
    return None


def get_related(root_dir: pathlib.Path, doc_id: str) -> dict | None:
    """Return incoming and outgoing wiki-link relationships for a document.

    Args:
        root_dir: Workspace root directory.
        doc_id: Stem of the document filename (without ``.md`` extension).

    Returns:
        Dict with keys ``doc_id``, ``outgoing`` (list of linked docs), and
        ``incoming`` (list of docs that link to this one), or ``None`` if
        the document does not exist in the graph.
    """
    from ..graph import VaultGraph

    graph = VaultGraph(root_dir)
    node = graph.nodes.get(doc_id)
    if node is None:
        return None

    outgoing = []
    for name in sorted(node.out_links):
        neighbor = graph.nodes.get(name)
        if neighbor:
            outgoing.append(
                {
                    "id": name,
                    "title": name,
                    "doc_type": neighbor.doc_type.value if neighbor.doc_type else "",
                }
            )

    incoming = []
    for name in sorted(node.in_links):
        neighbor = graph.nodes.get(name)
        if neighbor:
            incoming.append(
                {
                    "id": name,
                    "title": name,
                    "doc_type": neighbor.doc_type.value if neighbor.doc_type else "",
                }
            )

    return {"doc_id": doc_id, "outgoing": outgoing, "incoming": incoming}


def get_status(root_dir: pathlib.Path) -> dict:
    """Return vault status including document counts, features, and index health.

    The ``index`` sub-dict is populated only when GPU/RAG dependencies are
    available; otherwise it reports ``exists=False`` and zero counts.

    Args:
        root_dir: Workspace root directory.

    Returns:
        Dict with keys: ``total_docs``, ``types`` (counts by doc type),
        ``features`` (sorted list of feature tag names), and ``index``
        (dict with ``exists``, ``indexed_count``, ``device``, ``gpu_name``).
    """
    from ..metrics import get_vault_metrics
    from ..verification import list_features

    metrics = get_vault_metrics(root_dir)
    features = sorted(list_features(root_dir))

    result = {
        "total_docs": metrics.total_docs,
        "types": {dt.value: count for dt, count in metrics.counts_by_type.items()},
        "features": features,
        "index": {
            "exists": False,
            "indexed_count": 0,
            "device": None,
            "gpu_name": None,
        },
    }

    # Try to get index info if RAG deps are available
    try:
        from .embeddings import GPUNotAvailableError, get_device_info

        store = get_engine(root_dir).store
        result["index"]["indexed_count"] = store.count()
        result["index"]["exists"] = result["index"]["indexed_count"] > 0
        device_info = get_device_info()
        result["index"]["device"] = device_info["device"]
        result["index"]["gpu_name"] = device_info.get("gpu_name")
    except (ImportError, GPUNotAvailableError):
        logger.warning("RAG/GPU not available, skipping index info")
    except (FileNotFoundError, OSError) as e:
        logger.debug("Could not read index info: %s", e)

    return result


def index(root_dir: pathlib.Path, *, full: bool = False) -> IndexResult:
    """Index vault documents into the vector store.

    Args:
        root_dir: Workspace root directory.
        full: If ``True``, rebuild the entire index from scratch. If ``False``
            (default), only index documents that are new or have changed since
            the last run.

    Returns:
        IndexResult summarising documents added, updated, and skipped.

    Raises:
        Exception: Re-raises any error from engine initialization (e.g.,
            ``GPUNotAvailableError`` if no CUDA device is present).
    """
    try:
        engine = get_engine(root_dir)
    except Exception as e:
        logger.error("Failed to initialize RAG engine: %s", e)
        raise

    if full:
        return engine.indexer.full_index()
    return engine.indexer.incremental_index()


def search(
    root_dir: pathlib.Path,
    query: str,
    *,
    doc_type: str | None = None,
    feature: str | None = None,
    limit: int = 5,
) -> list[SearchResult]:
    """Semantic search over indexed vault documents.

    ``doc_type`` and ``feature`` filters are prepended to the query as
    ``type:<value>`` / ``feature:<value>`` tokens understood by the searcher.
    Returns an empty list (rather than raising) when the RAG engine is
    unavailable.

    Args:
        root_dir: Workspace root directory.
        query: Natural language search query.
        doc_type: Optional doc-type filter (e.g. ``"plan"``, ``"adr"``).
        feature: Optional feature-tag filter (e.g. ``"editor-demo"``).
        limit: Maximum number of results to return (default 5).

    Returns:
        List of SearchResult objects ordered by relevance, or an empty list
        when the vector index is unavailable.
    """
    try:
        engine = get_engine(root_dir)
    except Exception as e:
        logger.warning("Semantic search unavailable: %s", e)
        return []

    filter_parts: list[str] = []
    if doc_type:
        filter_parts.append(f"type:{doc_type}")
    if feature:
        filter_parts.append(f"feature:{feature}")

    enriched_query = " ".join([*filter_parts, query])
    return engine.searcher.search(enriched_query, top_k=limit)

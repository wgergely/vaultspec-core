"""LanceDB vector store layer for vault semantic search.

Manages the persistent .lance/ database with hybrid search (BM25 + ANN).
All heavy imports are guarded so core vault tools work without RAG deps.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    import pathlib

    import numpy as np

from rag.embeddings import EmbeddingModel

logger = logging.getLogger(__name__)

EMBEDDING_DIM = EmbeddingModel.DEFAULT_DIMENSION  # Default for schema creation


def _check_rag_deps() -> None:
    try:
        import lancedb  # noqa: F401
    except ImportError:
        raise ImportError(
            "RAG dependencies not installed. Run: pip install -e '.[rag]'"
        ) from None


def _sanitize_filter_value(value: str) -> str:
    """Escape a filter value for safe inclusion in SQL WHERE clauses.

    Escapes single quotes (SQL injection vector) and strips control
    characters. LanceDB does not support parameterized queries, so
    string escaping is the only defense.
    """
    sanitized = value.replace("'", "''")
    sanitized = "".join(c for c in sanitized if c.isprintable())
    return sanitized


def _parse_json_list(value: str) -> list[str]:
    """Deserialize a JSON list string, tolerating non-JSON input.

    If *value* is a valid JSON array it is returned as-is.  Otherwise the
    string is split on commas so that callers who stored plain
    comma-separated values don't cause a crash.
    """
    if not value or value == "[]":
        return []
    try:
        parsed = json.loads(value)
        if isinstance(parsed, list):
            return parsed
    except (json.JSONDecodeError, TypeError):
        pass
    # Fallback: treat as comma-separated
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass
class VaultDocument:
    """Schema for a single vault document in the vector store."""

    id: str  # document stem (e.g., "2026-02-12-rag-plan")
    path: str  # relative path (e.g., "plan/2026-02-12-rag-plan.md")
    doc_type: str  # "adr", "audit", "exec", "plan", "research", "reference"
    feature: str  # feature tag without # (e.g., "rag")
    date: str  # ISO date from frontmatter
    tags: str  # JSON-serialized list of tags
    related: str  # JSON-serialized list of related wiki-links
    title: str  # H1 heading extracted from body
    content: str  # full markdown body (for BM25 full-text search)
    vector: list[float] = field(default_factory=list)  # embedding vector

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for LanceDB insertion."""
        return {
            "id": self.id,
            "path": self.path,
            "doc_type": self.doc_type,
            "feature": self.feature,
            "date": self.date,
            "tags": self.tags,
            "related": self.related,
            "title": self.title,
            "content": self.content,
            "vector": self.vector,
        }

    @staticmethod
    def tags_to_json(tags: list[str]) -> str:
        return json.dumps(tags)

    @staticmethod
    def related_to_json(related: list[str]) -> str:
        return json.dumps(related)


class VaultStore:
    """LanceDB-backed vector store for vault documents.

    Storage lives at ``{root_dir}/.lance/``.  The table ``vault_docs``
    holds one row per indexed document with an embedding vector
    and full markdown content for Tantivy BM25 search.
    """

    TABLE_NAME = "vault_docs"

    def __init__(
        self, root_dir: pathlib.Path | str, embedding_dim: int | None = None
    ) -> None:
        _check_rag_deps()
        import pathlib as _pathlib

        import lancedb
        from core.config import get_config

        cfg = get_config()

        self.root_dir = _pathlib.Path(root_dir)
        self.db_path = self.root_dir / cfg.lance_dir
        self.db = lancedb.connect(str(self.db_path))
        self._embedding_dim = embedding_dim or EMBEDDING_DIM
        self._table = None
        self._fts_dirty = True  # track whether FTS index needs rebuild

    def close(self) -> None:
        """Release the LanceDB connection and table handle."""
        self._table = None
        self.db = None

    def __enter__(self) -> VaultStore:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> bool:
        self.close()
        return False

    def ensure_table(self) -> Any:
        """Create the vault_docs table if it doesn't exist.

        Returns the LanceDB Table handle.
        """
        if self._table is not None:
            return self._table

        import pyarrow as pa

        assert self.db is not None, "VaultStore is closed"
        existing = self.db.list_tables()
        if self.TABLE_NAME in existing:
            self._table = self.db.open_table(self.TABLE_NAME)
        else:
            schema = pa.schema(
                [
                    pa.field("id", pa.string()),
                    pa.field("path", pa.string()),
                    pa.field("doc_type", pa.string()),
                    pa.field("feature", pa.string()),
                    pa.field("date", pa.string()),
                    pa.field("tags", pa.string()),
                    pa.field("related", pa.string()),
                    pa.field("title", pa.string()),
                    pa.field("content", pa.string()),
                    pa.field("vector", pa.list_(pa.float32(), self._embedding_dim)),
                ]
            )
            empty = pa.table(
                {
                    name: pa.array([], type=f.type)
                    for name, f in zip(schema.names, schema, strict=True)
                },
                schema=schema,
            )
            self._table = self.db.create_table(self.TABLE_NAME, empty, mode="overwrite")
            logger.info(f"Created table '{self.TABLE_NAME}' at {self.db_path}")

        return self._table

    def _ensure_fts_index(self) -> None:
        """Rebuild the Tantivy FTS index on ``content`` if data has changed."""
        if not self._fts_dirty:
            return
        table = self.ensure_table()
        if table.count_rows() == 0:
            return
        table.create_fts_index("content", replace=True)
        self._fts_dirty = False
        logger.debug("Rebuilt FTS index on 'content' column")

    def upsert_documents(self, docs: list[VaultDocument]) -> None:
        """Insert or update documents by ``id``.

        Existing rows with matching ids are deleted first, then the new
        rows are appended.  The FTS index is marked dirty for lazy rebuild.
        """
        if not docs:
            return
        table = self.ensure_table()

        # Batch-delete existing rows for these ids
        ids = [d.id for d in docs]
        self._delete_by_ids(ids)

        # Add new rows
        records = [d.to_dict() for d in docs]
        table.add(records)
        self._fts_dirty = True
        logger.info("Upserted %d document(s)", len(docs))

    def delete_documents(self, ids: list[str]) -> None:
        """Remove documents by their ``id`` values."""
        if not ids:
            return
        self.ensure_table()
        self._delete_by_ids(ids)
        self._fts_dirty = True
        logger.info("Deleted %d document(s)", len(ids))

    def get_all_ids(self) -> set[str]:
        """Return the set of all document ``id`` values in the store."""
        table = self.ensure_table()
        if table.count_rows() == 0:
            return set()
        arrow_tbl = table.to_arrow()
        return set(arrow_tbl.column("id").to_pylist())

    def count(self) -> int:
        """Return total number of indexed documents."""
        table = self.ensure_table()
        return table.count_rows()

    def get_by_id(self, doc_id: str) -> dict | None:
        """Retrieve a single document by ID, or None if not found."""
        table = self.ensure_table()
        if table.count_rows() == 0:
            return None
        safe_id = _sanitize_filter_value(doc_id)
        results = table.search().where(f"id = '{safe_id}'").limit(1).to_list()
        if not results:
            return None
        row = results[0]
        row["tags"] = _parse_json_list(row.get("tags", "[]"))
        row["related"] = _parse_json_list(row.get("related", "[]"))
        row.pop("vector", None)
        return row

    def hybrid_search(
        self,
        query_vector: np.ndarray,
        query_text: str,
        filters: dict[str, str] | None = None,
        limit: int = 5,
    ) -> list[dict]:
        """Execute hybrid BM25 + ANN search with RRF reranking.

        Args:
            query_vector: Query embedding, shape ``(embedding_dim,)``.
            query_text: Raw text for BM25 full-text matching.
            filters: Optional metadata filters (``doc_type``, ``feature``,
                ``date`` as prefix match).
            limit: Maximum results to return.

        Returns:
            List of result dicts with all document columns plus
            ``_relevance_score``.  The ``tags`` and ``related`` fields are
            deserialized back to Python lists.  The ``vector`` column is
            stripped from results to save memory.
        """
        import numpy as np
        from lancedb.rerankers import RRFReranker

        table = self.ensure_table()
        if table.count_rows() == 0:
            return []

        # Ensure FTS index is current before hybrid search
        self._ensure_fts_index()

        query = (
            table.search(query_type="hybrid")
            .vector(np.asarray(query_vector, dtype=np.float32).tolist())
            .text(query_text)
            .rerank(RRFReranker())
            .limit(limit)
        )

        where_clause = self._build_where(filters)
        if where_clause:
            query = query.where(where_clause)

        try:
            results = query.to_list()
        except Exception as exc:
            logger.warning(
                "Hybrid search failed (%s), falling back to vector-only",
                exc,
                exc_info=True,
            )
            fallback = table.search(
                np.asarray(query_vector, dtype=np.float32).tolist()
            ).limit(limit)
            if where_clause:
                fallback = fallback.where(where_clause)
            results = fallback.to_list()

        # Post-process: deserialize JSON fields, drop vector
        for row in results:
            row["tags"] = _parse_json_list(row.get("tags", "[]"))
            row["related"] = _parse_json_list(row.get("related", "[]"))
            row.pop("vector", None)

        return results

    def _delete_by_ids(self, ids: list[str]) -> None:
        """Delete rows whose ``id`` is in *ids* using a single predicate."""
        if not ids:
            return
        table = self.ensure_table()
        # Escape single quotes in ids to prevent injection
        escaped = ", ".join(f"'{_sanitize_filter_value(i)}'" for i in ids)
        table.delete(f"id IN ({escaped})")

    _FilterKey = Literal["doc_type", "feature", "date"]

    @staticmethod
    def _build_where(filters: dict[str, str] | None) -> str | None:
        """Convert a filters dict into a LanceDB SQL WHERE clause.

        Filter values are sanitized to prevent SQL injection.
        """
        if not filters:
            return None
        parts: list[str] = []
        for key, value in filters.items():
            safe_value = _sanitize_filter_value(value)
            if key == "date":
                parts.append(f"date LIKE '{safe_value}%'")
            elif key in ("doc_type", "feature"):
                parts.append(f"{key} = '{safe_value}'")
        return " AND ".join(parts) if parts else None

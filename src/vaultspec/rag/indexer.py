"""Indexing pipeline for vault semantic search.

Scans vault documents, extracts metadata, generates embeddings, and
stores them in the LanceDB vector store. Supports full and incremental indexing.
"""

from __future__ import annotations

import contextlib
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pathlib

    from .embeddings import EmbeddingModel
    from .store import VaultStore

from ..vaultcore import DocType, get_doc_type, parse_vault_metadata, scan_vault
from .store import VaultDocument

logger = logging.getLogger(__name__)

__all__ = ["IndexResult", "VaultIndexer", "prepare_document"]


@dataclass
class IndexResult:
    """Result of an indexing operation.

    Attributes:
        total: Total number of docs in the index after the operation.
        added: Number of newly indexed documents.
        updated: Number of re-indexed (modified) documents.
        removed: Number of documents removed from the index.
        duration_ms: Wall-clock time for the operation in milliseconds.
        device: Compute device used for embeddings (e.g. ``"cuda"``, ``"cpu"``).
    """

    total: int  # total docs in index after operation
    added: int  # newly indexed
    updated: int  # re-indexed (modified)
    removed: int  # removed from index
    duration_ms: int  # wall-clock time
    device: str  # "cuda" (GPU required)


def _extract_title(body: str) -> str:
    """Extract first H1 heading from markdown body, or return empty string.

    Args:
        body: Raw markdown text to scan.

    Returns:
        The heading text (without the leading ``# ``), or ``""`` if none found.
    """
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def _extract_feature(metadata_tags: list[str]) -> str:
    """Extract the feature tag (non-directory tag) from the tag list.

    Args:
        metadata_tags: List of frontmatter tag strings (e.g. ``["#plan", "#rag"]``).

    Returns:
        The feature tag value without the leading ``#``, or ``""`` if none found.
    """
    for tag in metadata_tags:
        if not DocType.from_tag(tag):
            return tag.lstrip("#")
    return ""


def prepare_document(
    path: pathlib.Path, root_dir: pathlib.Path
) -> VaultDocument | None:
    """Prepare a single vault document for indexing (without vector).

    Reads the file, parses metadata, and constructs a VaultDocument
    with all fields except the vector (which is filled during embedding).

    Args:
        path: Absolute path to the markdown document file.
        root_dir: Workspace root directory used to compute the relative path.

    Returns:
        A ``VaultDocument`` with an empty vector, or ``None`` if the file
        cannot be read or has no recognised doc type.
    """
    try:
        content = path.read_text(encoding="utf-8")
    except Exception as e:
        logger.warning(f"Cannot read {path}: {e}")
        return None

    metadata, body = parse_vault_metadata(content)
    doc_type_enum = get_doc_type(path, root_dir)

    if doc_type_enum is None:
        return None

    from ..config import get_config

    docs_dir = root_dir / get_config().docs_dir
    try:
        rel_path = str(path.relative_to(docs_dir)).replace("\\", "/")
    except ValueError:
        rel_path = path.name

    title = _extract_title(body)
    if not title:
        title = path.stem

    feature = _extract_feature(metadata.tags)

    return VaultDocument(
        id=path.stem,
        path=rel_path,
        doc_type=doc_type_enum.value,
        feature=feature,
        date=metadata.date or "",
        tags=VaultDocument.tags_to_json(metadata.tags),
        related=VaultDocument.related_to_json(metadata.related),
        title=title,
        content=body.strip(),
        vector=[],  # filled during embedding step
    )


class VaultIndexer:
    """Orchestrates vault document indexing into the vector store."""

    def __init__(
        self,
        root_dir: pathlib.Path,
        model: EmbeddingModel,
        store: VaultStore,
    ) -> None:
        """Initialize the indexer with a workspace root, embedding model, and store.

        Args:
            root_dir: Path to the vault workspace root.
            model: Embedding model used to encode document text.
            store: Vector store where indexed documents are persisted.
        """
        from ..config import get_config

        cfg = get_config()

        self.root_dir = root_dir
        self.model = model
        self.store = store
        self._meta_path = root_dir / cfg.lance_dir / cfg.index_metadata_file

    def full_index(self) -> IndexResult:
        """Full re-index of all vault documents.

        Scans all documents, embeds them, and replaces the entire store.

        Returns:
            An ``IndexResult`` where ``added`` equals the total number of
            documents written and ``updated``/``removed`` are both zero.
        """
        start = time.time()

        # Scan and prepare all documents (concurrent I/O)
        # Keep path mapping for mtime metadata (must use scan paths, not reconstructed)
        paths = list(scan_vault(self.root_dir))
        path_by_stem: dict[str, pathlib.Path] = {p.stem: p for p in paths}
        docs = []
        with ThreadPoolExecutor() as pool:
            futures = [pool.submit(prepare_document, p, self.root_dir) for p in paths]
            for future in futures:
                try:
                    doc = future.result()
                except Exception:
                    logger.warning("Worker failed to prepare document", exc_info=True)
                    continue
                if doc is not None:
                    docs.append(doc)

        if not docs:
            return IndexResult(
                total=0,
                added=0,
                updated=0,
                removed=0,
                duration_ms=0,
                device=self.model.device,
            )

        # Batch-embed all document texts
        texts = [f"{d.title}\n\n{d.content}" for d in docs]
        vectors = self.model.encode_documents(texts)

        # Assign vectors to documents
        for doc, vec in zip(docs, vectors, strict=True):
            doc.vector = vec.tolist()

        # Clear existing table and write all documents
        self.store.ensure_table()
        # Delete all existing docs
        try:
            existing_ids = self.store.get_all_ids()
            if existing_ids:
                self.store.delete_documents(list(existing_ids))
        except OSError:
            logger.error(
                "Failed to delete existing documents during full "
                "re-index — aborting to prevent duplicates"
            )
            raise

        self.store.upsert_documents(docs)

        # Save metadata using the original scan paths (not reconstructed paths)
        self._save_meta_from_paths(path_by_stem)

        duration_ms = int((time.time() - start) * 1000)
        return IndexResult(
            total=len(docs),
            added=len(docs),
            updated=0,
            removed=0,
            duration_ms=duration_ms,
            device=self.model.device,
        )

    def incremental_index(self) -> IndexResult:
        """Incremental index: only re-index new and modified documents.

        Compares file mtimes against stored metadata to identify changes.

        Returns:
            An ``IndexResult`` with counts for newly added, updated, and
            removed documents since the last index run.
        """
        start = time.time()

        # Load previous index metadata
        prev_meta = self._load_meta()

        # Scan current vault state
        current_docs: dict[str, pathlib.Path] = {}
        for path in scan_vault(self.root_dir):
            doc_type = get_doc_type(path, self.root_dir)
            if doc_type is not None:
                current_docs[path.stem] = path

        # Get stored document ids
        stored_ids = self.store.get_all_ids()

        # Identify changes
        current_ids = set(current_docs.keys())
        new_ids = current_ids - stored_ids
        deleted_ids = stored_ids - current_ids
        potentially_modified = current_ids & stored_ids

        # Check mtimes for modified files
        modified_ids = set()
        for doc_id in potentially_modified:
            path = current_docs[doc_id]
            current_mtime = path.stat().st_mtime
            prev_mtime = prev_meta.get(doc_id, 0)
            if current_mtime > prev_mtime:
                modified_ids.add(doc_id)

        # Prepare documents that need (re-)embedding (concurrent I/O)
        to_index_ids = new_ids | modified_ids
        docs_to_index = []
        if to_index_ids:
            paths_to_index = [current_docs[doc_id] for doc_id in to_index_ids]
            with ThreadPoolExecutor() as pool:
                results = pool.map(
                    lambda p: prepare_document(p, self.root_dir),
                    paths_to_index,
                )
                for doc in results:
                    if doc is not None:
                        docs_to_index.append(doc)

        # Embed new/modified documents
        if docs_to_index:
            texts = [f"{d.title}\n\n{d.content}" for d in docs_to_index]
            vectors = self.model.encode_documents(texts)
            for doc, vec in zip(docs_to_index, vectors, strict=True):
                doc.vector = vec.tolist()
            self.store.upsert_documents(docs_to_index)

        # Delete removed documents
        if deleted_ids:
            self.store.delete_documents(list(deleted_ids))

        # Update metadata for all current docs (paths only, no re-parsing)
        self._save_meta_from_paths(current_docs)

        total = self.store.count()
        duration_ms = int((time.time() - start) * 1000)
        return IndexResult(
            total=total,
            added=len(new_ids),
            updated=len(modified_ids),
            removed=len(deleted_ids),
            duration_ms=duration_ms,
            device=self.model.device,
        )

    def _save_meta(self, docs: list[VaultDocument]) -> None:
        """Save index metadata (file mtimes) from VaultDocument list.

        Args:
            docs: List of indexed documents whose paths are used to read mtimes.
        """
        meta = {}
        from ..config import get_config

        docs_dir = self.root_dir / get_config().docs_dir
        for doc in docs:
            path = docs_dir / doc.path
            with contextlib.suppress(OSError):
                meta[doc.id] = path.stat().st_mtime
        self._write_meta(meta)

    def _save_meta_from_paths(self, docs: dict[str, pathlib.Path]) -> None:
        """Save index metadata (file mtimes) directly from path dict.

        Avoids re-parsing documents just to record their mtimes.

        Args:
            docs: Mapping of document stem to its absolute ``Path``.
        """
        meta = {}
        for doc_id, path in docs.items():
            with contextlib.suppress(OSError):
                meta[doc_id] = path.stat().st_mtime
        self._write_meta(meta)

    def _write_meta(self, meta: dict[str, float]) -> None:
        """Write mtime metadata to the sidecar JSON file.

        Args:
            meta: Mapping of document stem to ``st_mtime`` float value.
        """
        self._meta_path.parent.mkdir(parents=True, exist_ok=True)
        self._meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    def _load_meta(self) -> dict[str, float]:
        """Load index metadata from the sidecar JSON file.

        Returns:
            Mapping of document stem to ``st_mtime`` float, or an empty
            dict if the file does not exist or cannot be parsed.
        """
        if not self._meta_path.exists():
            return {}
        try:
            return json.loads(self._meta_path.read_text(encoding="utf-8"))
        except (KeyError, ValueError, OSError):
            return {}

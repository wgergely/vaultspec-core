"""RAG unit test fixtures."""

import pathlib
import shutil
import time

import pytest
from tests.constants import (
    GPU_FAST_CORPUS_STEMS,
    LANCE_SUFFIX_UNIT,
    TEST_PROJECT,
)


def _fast_index(indexer, model, store, root, stems):
    """Index only the given subset of document stems."""
    from rag.indexer import IndexResult, prepare_document
    from vault.scanner import scan_vault

    start = time.time()

    paths = [p for p in scan_vault(root) if p.stem in stems]
    docs = []
    for p in paths:
        doc = prepare_document(p, root)
        if doc is not None:
            docs.append(doc)

    if not docs:
        return IndexResult(
            total=0,
            added=0,
            updated=0,
            removed=0,
            duration_ms=0,
            device=model.device,
        )

    texts = [f"{d.title}\n\n{d.content}" for d in docs]
    vectors = model.encode_documents(texts)

    for doc, vec in zip(docs, vectors, strict=True):
        doc.vector = vec.tolist()

    store.ensure_table()
    store.upsert_documents(docs)

    indexer._save_meta(docs)

    duration_ms = int((time.time() - start) * 1000)
    return IndexResult(
        total=len(docs),
        added=len(docs),
        updated=0,
        removed=0,
        duration_ms=duration_ms,
        device=model.device,
    )


def _build_rag_components(
    root: pathlib.Path, *, fast: bool, lance_suffix: str = ""
) -> dict:
    """Build real RAG components on CUDA GPU."""
    from rag.embeddings import EmbeddingModel
    from rag.indexer import VaultIndexer
    from rag.store import VaultStore

    lance_name = f".lance{lance_suffix}"
    lance_dir = root / lance_name

    if lance_dir.exists():
        shutil.rmtree(lance_dir)

    model = EmbeddingModel()
    store = VaultStore.__new__(VaultStore)
    import lancedb

    store.root_dir = root
    store.db_path = lance_dir
    store.db = lancedb.connect(str(lance_dir))
    store._table = None
    store._fts_dirty = True

    indexer = VaultIndexer(root, model, store)

    if fast:
        result = _fast_index(indexer, model, store, root, GPU_FAST_CORPUS_STEMS)
    else:
        result = indexer.full_index()

    return {
        "model": model,
        "store": store,
        "indexer": indexer,
        "index_result": result,
        "root": root,
        "lance_dir": lance_dir,
    }


@pytest.fixture(scope="session")
def rag_components():
    """Set up real RAG components once for the entire test session (GPU only).

    Indexes a 13-doc subset covering all 5 doc_types and key features.
    Uses .lance-fast-unit/ to avoid colliding with integration fixtures.
    """
    components = _build_rag_components(
        TEST_PROJECT, fast=True, lance_suffix=LANCE_SUFFIX_UNIT
    )

    yield components

    lance_dir = components["lance_dir"]
    if lance_dir.exists():
        shutil.rmtree(lance_dir)

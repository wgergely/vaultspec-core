from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys
import time

import pytest

# Add the library to the path once at the top-level conftest.
# This avoids doing it in every single test file.
# Ideally, the user would run pytest with PYTHONPATH=.vaultspec/lib/src
_VAULTSPEC = pathlib.Path(__file__).resolve().parent.parent
LIB_SRC = _VAULTSPEC / "lib" / "src"
SCRIPTS = _VAULTSPEC / "scripts"
for _p in (LIB_SRC, SCRIPTS):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from protocol.providers.base import GeminiModels  # noqa: E402

# Check if RAG deps are available
try:
    import lancedb  # noqa: F401
    import sentence_transformers  # noqa: F401
    import torch  # noqa: F401

    HAS_RAG = True
except ImportError:
    HAS_RAG = False

TEST_PROJECT = pathlib.Path(__file__).resolve().parent.parent.parent / "test-project"

# GPU fast corpus: 13 representative docs covering all 5 doc_types and
# key features needed by the test suite.  Avoids embedding all 213 docs.
GPU_FAST_CORPUS_STEMS: frozenset[str] = frozenset(
    [
        # adr (4) -- architecture, editor-demo, displaymap, dispatch
        "2026-02-05-editor-demo-architecture",
        "2026-02-06-displaymap-architecture-design",
        "2026-02-06-main-window-architecture",
        "2026-02-07-dispatch-architecture",
        # plan (2) -- editor-demo feature, main-window
        "2026-02-05-editor-demo-phase1-plan",
        "2026-02-06-main-window-master-plan",
        # exec (2) -- editor-demo feature, layout
        "2026-02-05-turn-completion-summary",
        "2026-02-06-layout-alignment-summary",
        # reference (3) -- safety-audit, editor-demo, displaymap
        "2026-02-07-main-window-safety-audit",
        "2026-02-05-editor-demo-core-reference",
        "2026-02-04-displaymap-reference",
        # research (2) -- editor-demo, dispatch
        "2026-02-05-editor-demo-research",
        "2026-02-07-dispatch-protocol-alignment-audit",
    ]
)

# CPU is NOT supported.  All tests require CUDA GPU.
# If running without GPU, tests that need RAG components will be skipped.


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

    # Save metadata for incremental indexing
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
    """Build real RAG components on CUDA GPU.

    When ``fast=True``, indexes a 13-doc subset covering all doc_types
    and key features.  When ``fast=False``, indexes the full corpus.

    ``lance_suffix`` isolates the lance directory so that the fast and
    full fixtures don't share the same ``.lance/`` path and corrupt each
    other's data files.

    Raises:
        GPUNotAvailableError: If no CUDA GPU is available. CPU is not
            supported — tests will fail fast with a clear error.
    """
    from rag.embeddings import EmbeddingModel
    from rag.indexer import VaultIndexer
    from rag.store import VaultStore

    lance_name = f".lance{lance_suffix}"
    lance_dir = root / lance_name

    # Clean up any previous test data
    if lance_dir.exists():
        shutil.rmtree(lance_dir)

    model = EmbeddingModel()  # Fails fast if no CUDA GPU
    store = VaultStore.__new__(VaultStore)
    # Manually init with custom lance path to avoid sharing
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
    Requires CUDA GPU — fails fast with GPUNotAvailableError otherwise.
    Uses .lance-fast/ to avoid colliding with the full-corpus fixture.
    """
    components = _build_rag_components(TEST_PROJECT, fast=True, lance_suffix="-fast")

    yield components

    lance_dir = components["lance_dir"]
    if lance_dir.exists():
        shutil.rmtree(lance_dir)


@pytest.fixture(scope="session")
def rag_components_full():
    """Set up real RAG components with the FULL 213-doc corpus.

    Only used by tests marked @pytest.mark.quality that need full-corpus
    coverage (quality precision tests, document count assertions, etc.).
    Uses .lance-full/ to avoid colliding with the fast fixture.
    """
    components = _build_rag_components(TEST_PROJECT, fast=False, lance_suffix="-full")

    yield components

    lance_dir = components["lance_dir"]
    if lance_dir.exists():
        shutil.rmtree(lance_dir)


@pytest.fixture
def require_gpu_corpus(rag_components):
    """Assert GPU corpus is available (always true with GPU-only policy).

    Kept for backward compatibility with test files that reference it.
    Since CPU is no longer supported, this is effectively a no-op.
    """
    assert rag_components["model"].device == "cuda", "GPU required"


def _cleanup_test_project(root: pathlib.Path) -> None:
    """Remove transient artifacts, preserving .vault/ and README."""
    for item in root.iterdir():
        if item.name in (".vault", "README.md", ".gitignore"):
            continue
        if item.is_dir():
            shutil.rmtree(item, ignore_errors=True)
        else:
            item.unlink(missing_ok=True)


@pytest.fixture(scope="session", autouse=True)
def _vault_snapshot_reset():
    """Reset test-project/.vault/ to git HEAD after the full test session."""
    yield
    subprocess.run(
        ["git", "checkout", "--", "test-project/.vault/"],
        cwd=pathlib.Path(__file__).resolve().parent.parent.parent,
        check=False,
    )


@pytest.fixture
def test_agent_md():
    return f"""---
tier: LOW
model: {GeminiModels.LOW}
description: "A test agent"
---

# Agent Persona
You are a helpful French Baker.
"""

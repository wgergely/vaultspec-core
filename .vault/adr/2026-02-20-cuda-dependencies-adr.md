---
tags:
  - "#adr"
  - "#cuda-dependencies"
date: "2026-02-20"
related:
  - "[[2026-02-20-cuda-dependencies-audit-research]]"
  - "[[2026-02-12-rag-embeddings-adr]]"
  - "[[2026-02-12-rag-vectordb-adr]]"
  - "[[2026-02-12-rag-retrieval-adr]]"
---
# `cuda-dependencies` adr: Elevate RAG Dependency Floors to Frontier Versions | (**status:** `accepted`)

## Problem Statement

The RAG subsystem mandates **Python 3.13+** and **CUDA 13.0+** as a deliberate frontier stance. However, dependency floors in `pyproject.toml` are stale and contradictory: `torch>=2.5.0` has no cu130 wheel, `sentence-transformers>=3.0.0` is two years behind current, `lancedb>=0.15.0` predates critical features the code depends on, and in-code error messages reference the wrong CUDA index URL (`cu124` instead of `cu130`). These mismatches cause installation failures, misleading diagnostics, and unnecessary import-time coupling.

See [[2026-02-20-cuda-dependencies-audit-research]] for the full audit.

## Considerations

- **Frontier mandate is non-negotiable.** CUDA 13.0 and Python 3.13 are deliberate. The fix is raising floors, not lowering targets.
- **cu130 wheels start at torch 2.9.0.** Torch 2.5–2.8 have no cu130 builds. The current floor permits pip to resolve a version with no cu130 wheel, breaking the install.
- **sentence-transformers 5.x** ships with Transformers v5 compatibility, Python 3.13 improvements, and is the current stable line.
- **lancedb 0.15 is ancient.** The codebase uses `RRFReranker`, `create_fts_index(replace=True)`, and hybrid search patterns that stabilized in 0.20+. Known float32 bugs in 0.18 are fixed in later versions.
- **`--extra-index-url` is required** (not `--index-url`) for torch cu130 installs due to the `cuda-bindings` mirroring gap.
- **`store.py` imports `EmbeddingModel` at module level** solely to read a constant (`DEFAULT_DIMENSION = 768`), pulling torch into processes that only need lancedb.

## Constraints

- No breaking changes to the RAG public API (`rag.api` functions).
- The `nomic-embed-text-v1.5` model requires GPU compute capability >= 7.5 (Turing+). This is a hardware constraint, not a software one — document it, don't try to work around it.
- The `--extra-index-url` flag cannot be embedded in `pyproject.toml` — it must be communicated via documentation and error messages.

## Implementation

Six changes, grouped by scope:

### I1. Raise dependency floors in `pyproject.toml`

Update `[project.optional-dependencies] rag`:

```toml
rag = [
    "torch>=2.9.0",
    "sentence-transformers>=5.0.0",
    "lancedb>=0.27.0",
    "einops>=0.8.0",  # transitive dep of nomic-embed-text-v1.5 (trust_remote_code)
]
```

### I2. Fix `_require_cuda()` error message in `embeddings.py`

Replace the hardcoded `cu124` / `--index-url` with `cu130` / `--extra-index-url`:

```python
raise GPUNotAvailableError(
    f"CUDA GPU required but not available. "
    f"Torch version: {torch_version}, CUDA compiled: {cuda_version}. "
    f"vaultspec requires CUDA 13.0+ with compute capability >= 7.5. "
    f"Install CUDA-enabled PyTorch: "
    f"pip install torch --extra-index-url https://download.pytorch.org/whl/cu130"
)
```

### I3. Decouple `store.py` module-level import

Replace:

```python
from rag.embeddings import EmbeddingModel
EMBEDDING_DIM = EmbeddingModel.DEFAULT_DIMENSION
```

With:

```python
EMBEDDING_DIM = 768  # nomic-embed-text-v1.5 default; matches EmbeddingModel.DEFAULT_DIMENSION
```

### I4. Add compute capability requirement to documentation

Add to `README.md`, `docs/getting-started.md`, and `docs/search-guide.md`:

> **GPU:** NVIDIA GPU with compute capability >= 7.5 (Turing architecture or newer: RTX 2000+, T4+, A-series, H-series)

### I5. Standardize `--extra-index-url` in all install references

Audit and fix every occurrence of `--index-url` to `--extra-index-url` across:

- `README.md`
- `docs/getting-started.md`
- `docs/search-guide.md`
- `embeddings.py` error message (covered by I2)

Add a prominent warning box in `docs/getting-started.md`:

> **Important:** Always use `--extra-index-url` (not `--index-url`) when installing RAG dependencies. Without this flag, pip installs CPU-only PyTorch from PyPI, which will fail at runtime with `GPUNotAvailableError`.

### I6. Add `VAULTSPEC_RAG_ENABLED` config override

Add a new config variable to `core/config.py`:

```python
ConfigVariable(
    env_name="VAULTSPEC_RAG_ENABLED",
    attr_name="rag_enabled",
    var_type=bool,
    default=True,
    description="Enable/disable RAG features. Set to false in GPU-less environments.",
)
```

Check this in `api.py:get_engine()` before calling `_require_cuda()`. When `false`, `get_engine()` raises `ImportError("RAG disabled by configuration")` to trigger existing fallback paths.

## Rationale

- **Raising floors eliminates the contradiction.** With `torch>=2.9.0`, every resolvable version has a cu130 wheel. The spec becomes self-consistent with the CUDA 13.0 mandate.
- **Frontier versions are stable.** torch 2.9+, sentence-transformers 5.x, and lancedb 0.27+ are all current stable releases, not bleeding-edge nightlies.
- **Inlining `EMBEDDING_DIM`** is a trivial change that eliminates an unnecessary torch import in the store module. The value is a constant of the model architecture and will not change without a model migration (which would touch far more code).
- **`--extra-index-url` is a PyTorch ecosystem standard.** The `--index-url` variant fails for torch 2.10+ due to the `cuda-bindings` gap. Using `--extra-index-url` everywhere avoids this class of bug entirely.
- **`VAULTSPEC_RAG_ENABLED`** follows the existing config pattern and reuses the `ImportError` fallback path already present in Tier 1 functions — no new error handling needed.

## Consequences

- **Users on torch 2.5–2.8 must upgrade.** This is intentional — those versions cannot satisfy the cu130 mandate anyway.
- **Users on sentence-transformers 3.x or 4.x must upgrade.** Models saved with older sentence-transformers versions may need re-downloading (the embedding model is pulled from HuggingFace Hub, not serialized locally, so this is a no-op for vaultspec).
- **Users on lancedb < 0.27 must upgrade.** The `.lance/` directory format is forward-compatible, but users should re-index after upgrading to benefit from fixes.
- **The `EMBEDDING_DIM = 768` inline is a maintenance coupling.** If the embedding model ever changes, this constant must be updated manually. A code comment marks the dependency.
- **`VAULTSPEC_RAG_ENABLED=false` disables all Tier 2 operations.** Users in GPU-less environments lose search and indexing but retain all Tier 1 vault management.

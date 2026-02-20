---
tags:
  - "#plan"
  - "#cuda-dependencies"
date: "2026-02-20"
related:
  - "[[2026-02-20-cuda-dependencies-adr]]"
  - "[[2026-02-20-cuda-dependencies-audit-research]]"
---

# `cuda-dependencies` `p1` plan

Align the RAG dependency stack with the project's CUDA 13.0+ / Python 3.13+ frontier
mandate. Raises stale dependency floors, fixes error messages, decouples an unnecessary
import, centralizes the CUDA version constant, adds a config override, and improves
documentation.

## Proposed Changes

Per [[2026-02-20-cuda-dependencies-adr]] (accepted), six implementation items are
required. The user has additionally requested that all `cu130` string references be
centralized into a single constant to avoid future hardcoding drift.

This plan restructures the ADR's six items into four execution phases: a core constants
phase (centralized CUDA version + config override), a dependency/code phase (floors +
embeddings + store), a documentation phase, and a verification phase.

## Tasks

- `Phase 1: Central CUDA constant and config override`
    1. `Add CUDA_INDEX_TAG constant to embeddings.py` — Define `CUDA_INDEX_TAG = "cu130"` and `CUDA_INDEX_URL = f"https://download.pytorch.org/whl/{CUDA_INDEX_TAG}"` at the top of `embeddings.py` (alongside the existing `GPUNotAvailableError`). This becomes the single source of truth for the CUDA wheel identifier. All downstream references use this constant.
    2. `Add VAULTSPEC_RAG_ENABLED to config registry` — Add a new `ConfigVariable` entry to `CONFIG_REGISTRY` in `core/config.py` with `env_name="VAULTSPEC_RAG_ENABLED"`, `attr_name="rag_enabled"`, `var_type=bool`, `default=True`. Add the corresponding `rag_enabled: bool = True` field to the `VaultSpecConfig` dataclass under the `# -- RAG` section.
    3. `Wire rag_enabled into api.py:get_engine()` — Before the `_require_cuda()` call in `get_engine()`, check `get_config().rag_enabled`. When `False`, raise `ImportError("RAG disabled by configuration (VAULTSPEC_RAG_ENABLED=false)")` to trigger the existing Tier 1 fallback paths.

- `Phase 2: Dependency floors and code fixes`
    1. `Raise dependency floors in pyproject.toml` — Update the `[project.optional-dependencies] rag` section: `torch>=2.9.0`, `sentence-transformers>=5.0.0`, `lancedb>=0.27.0`, `einops>=0.8.0`. Add a comment on the `einops` line noting it is a transitive dependency of `nomic-embed-text-v1.5`.
    2. `Fix _require_cuda() error message` — Update the `GPUNotAvailableError` message in `embeddings.py:48-53` to use the centralized `CUDA_INDEX_URL` constant and `--extra-index-url` flag. Include the CUDA 13.0 mandate and compute capability >= 7.5 requirement in the message text.
    3. `Decouple store.py module-level import` — Remove `from rag.embeddings import EmbeddingModel` (line 19) and replace `EMBEDDING_DIM = EmbeddingModel.DEFAULT_DIMENSION` (line 23) with `EMBEDDING_DIM = 768` plus a comment linking it to `EmbeddingModel.DEFAULT_DIMENSION`.

- `Phase 3: Documentation updates`
    1. `Add compute capability requirement to docs` — Add a "GPU: compute capability >= 7.5 (Turing+)" line to the prerequisites sections of `README.md`, `docs/getting-started.md`, and `docs/search-guide.md`.
    2. `Add nvcc vs nvidia-smi note to getting-started.md` — In the prerequisites section, clarify that `nvidia-smi` shows the driver CUDA compatibility version, and `nvcc --version` shows the toolkit version.
    3. `Standardize --extra-index-url in all install references` — Audit `README.md`, `docs/getting-started.md`, `docs/search-guide.md`, and `docs/guides/individual-developer.md` for any occurrence of `--index-url` (without the `extra-` prefix) and replace with `--extra-index-url`. Add a prominent warning callout in `docs/getting-started.md` explaining why `--extra-index-url` is required.
    4. `Strengthen README Quick Start note` — Expand the `> **Note:**` block after the install command in `README.md` to explicitly warn that omitting `--extra-index-url` installs CPU-only PyTorch, which will fail at runtime. Mention compute capability >= 7.5 and the raised dependency floors (torch >= 2.9.0, CUDA 13.0+) so the README serves as the authoritative first-contact for CUDA install requirements.
    5. `Add VAULTSPEC_RAG_ENABLED to search-guide.md config table` — Document the new config variable in the Configuration section of the search guide.

- `Phase 4: Verification`
    1. `Run test suite` — Execute `pytest` to confirm no regressions. The store import decoupling and config addition should not break existing tests.
    2. `Grep audit for stale references` — Search the entire codebase for any remaining `cu124`, bare `--index-url` (without `extra-`), or hardcoded `768` references that should use the centralized constants.

## Parallelization

- Phase 1 steps are sequential (1.1 defines the constant, 1.2 and 1.3 consume it).
- Phase 2 steps are independent and can be parallelized (pyproject.toml, embeddings.py, store.py are separate files).
- Phase 3 steps are independent across files and can be parallelized.
- Phase 4 must follow Phases 1–3.

## Verification

- All existing tests pass (`pytest`).
- `grep -r "cu124"` across `*.py` and `*.md` returns zero hits.
- `grep -r "\-\-index-url" --include="*.py" --include="*.md"` returns only `--extra-index-url` matches (no bare `--index-url`).
- `store.py` no longer imports from `rag.embeddings` — confirmed by checking the import block.
- `VAULTSPEC_RAG_ENABLED=false` in the environment causes `get_engine()` to raise `ImportError` (manual or test-level verification).
- All documentation prereq sections mention compute capability >= 7.5.

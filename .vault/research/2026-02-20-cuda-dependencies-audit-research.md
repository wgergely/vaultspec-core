---
tags:
  - "#research"
  - "#cuda-dependencies"
date: "2026-02-20"
related:
  - "[[2026-02-12-rag-embeddings-adr]]"
  - "[[2026-02-12-rag-vectordb-adr]]"
  - "[[2026-02-12-rag-retrieval-adr]]"
---

# `cuda-dependencies` research: RAG CUDA Environment Audit

Full audit of the CUDA dependency stack powering the RAG subsystem. Covers documentation accuracy, in-code warnings, CUDA/Python version compatibility, graceful degradation, and pip install correctness.

## Findings

### 1. Documentation State

**Verdict: Contains critical errors that will break user installs.**

All documentation references **CUDA 13.0+** and the `cu130` index URL, which is factually correct (CUDA 13.0 was released August 2025, cu130 wheels exist on `download.pytorch.org`). However, there are several issues:

#### Files audited

| File | CUDA claim | Install command |
|------|-----------|-----------------|
| `README.md:44` | "CUDA 13.0+" | `pip install -e ".[rag,dev]" --extra-index-url https://download.pytorch.org/whl/cu130` |
| `docs/getting-started.md:9` | "CUDA 13.0+" | Same cu130 URL |
| `docs/getting-started.md:244` | Troubleshooting section | `pip install torch --extra-index-url https://download.pytorch.org/whl/cu130` |
| `docs/search-guide.md:78` | "CUDA: 13.0+" | N/A |

#### Issues found

- **A1 - Overly narrow CUDA floor.** Requiring CUDA 13.0+ excludes users on CUDA 12.x (12.1, 12.4, 12.6, 12.8, 12.9), which remain extremely common in production. The `nomic-embed-text-v1.5` model runs on any GPU with compute capability >= 7.5 and CUDA >= 11.8. The `pyproject.toml` specifies `torch>=2.5.0`, but PyTorch 2.5 shipped with cu118 and cu124 wheels — not cu130 (which requires PyTorch >= 2.9). There is a mismatch: the floor version `torch>=2.5.0` doesn't have cu130 builds.
- **A2 - No mention of compute capability requirement.** The `nomic-embed-text-v1.5` model requires compute capability >= 7.5 (Turing or newer). Users with older GPUs (Pascal, Volta) will get cryptic CUDA errors with no guidance.
- **A3 - No `nvcc --version` vs `nvidia-smi` distinction.** Documentation tells users to run `nvidia-smi` to verify CUDA, but `nvidia-smi` shows the driver's CUDA compatibility version, not the toolkit version. This is a common source of confusion.
- **A4 - `pyproject.toml` uses `--extra-index-url` in docs but specifies no index in the dependency spec.** The `[project.optional-dependencies] rag` section lists `torch>=2.5.0` without constraining the index URL. A bare `pip install -e ".[rag]"` will pull the CPU-only torch from PyPI, then the user gets `GPUNotAvailableError` at runtime. This is the #1 installation footgun.
- **A5 - `extension.toml` installs only `.[dev]`.** The runtime install command (`pip install -e '.[dev]'`) does not include `[rag]` extras at all. Users relying on extension-based installs will never get RAG deps.

### 2. In-Code Warning Messages

**Verdict: Good structure, but messages reference a hardcoded cu124 URL that contradicts docs.**

#### Warning/error inventory

| Location | Type | Message quality |
|----------|------|----------------|
| `embeddings.py:19-23` | `GPUNotAvailableError` class | Clear custom exception |
| `embeddings.py:25-33` | `_check_rag_deps()` | Clear: tells user to run `pip install -e '.[rag]'` |
| `embeddings.py:36-53` | `_require_cuda()` | **Problem**: hardcodes `cu124` in install hint |
| `embeddings.py:63-66` | `get_device_info()` | Calls both checks, good |
| `embeddings.py:112-114` | `EmbeddingModel.__init__` | Calls both checks, good |
| `api.py:107-132` | `get_engine()` | Calls `_require_cuda()`, catches exceptions, good |
| `api.py:206-208` | `get_document()` | Catches `ImportError` with debug log, good |
| `api.py:326-329` | `get_status()` | Catches `ImportError` and `FileNotFoundError`, good |
| `docs.py:119,145` | CLI epilog | "Requires NVIDIA GPU with CUDA" — adequate |
| `docs.py:374-376` | `handle_index` ImportError | "RAG dependencies not installed" — adequate |
| `docs.py:425-427` | `handle_search` ImportError | Same — adequate |

#### Issues found

- **B1 - `_require_cuda()` hardcodes `cu124`.** Line 52 says `pip install torch --index-url https://download.pytorch.org/whl/cu124`. This contradicts all documentation which says `cu130`. Neither is universally correct — the user's install URL depends on their local CUDA toolkit version.
- **B2 - No runtime detection of CUDA toolkit version.** The code checks `torch.cuda.is_available()` and reports `torch.version.cuda` (the version torch was compiled against), but never checks what CUDA toolkit is actually installed on the system. A mismatch between these causes silent failures.
- **B3 - `store.py:20` imports `EmbeddingModel` at module level.** This triggers the full torch import chain just to read `DEFAULT_DIMENSION = 768`. If torch isn't installed, importing `rag.store` fails even though the store itself only needs `lancedb`.

### 3. CUDA Version Audit

**Verdict: The cu130 pin is too aggressive; the torch>=2.5.0 floor is inconsistent with it.**

| Component | Version claimed | Actual compatibility |
|-----------|----------------|---------------------|
| CUDA Toolkit | 13.0+ required | CUDA 11.8+ works for nomic-embed-text-v1.5 |
| PyTorch | `>=2.5.0` | 2.5.x ships cu118/cu124. cu130 requires >=2.9.0 |
| sentence-transformers | `>=3.0.0` | Latest is 5.2. Requires PyTorch >= 1.11 |
| lancedb | `>=0.15.0` | Latest is 0.29.2. Uses stable ABI from Python 3.9+ |
| einops | `>=0.7.0` | Pure Python, no CUDA dependency |
| nomic-embed-text-v1.5 | Not pinned | ~262MB model, compute capability >= 7.5 |

#### Issues found

- **C1 - torch>=2.5.0 + cu130 is contradictory.** If a user installs `torch==2.5.0` (the minimum), there is no cu130 wheel for it. cu130 starts at torch 2.9.0. Either raise the torch floor to `>=2.9.0` to match the cu130 documentation, or lower the CUDA requirement to support cu118/cu124 which work with torch 2.5+.
- **C2 - No upper bound on torch.** sentence-transformers sometimes breaks with new torch major versions. No cap means a future torch release could silently break the RAG pipeline.
- **C3 - lancedb 0.15 is ancient.** Current stable is 0.29.2. Version 0.15 may have float32 bugs and missing hybrid search features that the code depends on (e.g., `RRFReranker`). The floor should be raised.

### 4. Python Version Audit

**Verdict: Python 3.13 requirement is valid but creates friction.**

| Component | Python 3.13 support |
|-----------|-------------------|
| PyTorch | Supported since 2.6 (Jan 2025). 2.10.0 officially supports 3.10-3.14. |
| sentence-transformers | Supports `>=3.9`. Works on 3.13 when PyTorch is installed. |
| lancedb | Stable ABI `cp39-abi3`, works on 3.13. |
| einops | Pure Python, works on 3.13. |

- **D1 - pyproject.toml requires `>=3.13`.** This is stricter than any dependency requires. PyTorch 2.6+ supports 3.13, but the torch floor is 2.5.0 which didn't support 3.13 yet. This creates another inconsistency: a user on Python 3.13 cannot install torch 2.5.0 (no wheel exists), so the effective minimum is torch 2.6+ anyway.

### 5. Graceful Degradation / Disconnect

**Verdict: RAG correctly disables when deps are missing, but GPU absence is a hard fatal.**

#### What works

- Tier 1 functions (`list_documents`, `get_document` filesystem fallback, `get_related`, `get_status`) work without RAG deps via `ImportError` catches.
- `get_document()` falls back to filesystem scan when store lookup fails.
- `get_status()` returns `index.exists=False` and `index.device=None` when RAG is unavailable.
- Tests use `pytest.mark.skipif(not HAS_RAG, ...)` to skip RAG tests cleanly.
- CLI commands (`docs.py index`, `docs.py search`) catch `ImportError` and print actionable install instructions.

#### What doesn't work

- **E1 - `GPUNotAvailableError` is fatal with no bypass.** If torch is installed but CUDA isn't available (e.g., CPU-only machine that happens to have torch), `get_engine()` raises `GPUNotAvailableError` with no way to disable RAG at the config level. There should be a `VAULTSPEC_RAG_ENABLED=false` or `VAULTSPEC_DEVICE=cpu` override.
- **E2 - No CPU fallback path.** The codebase explicitly forbids CPU: "CPU is NOT supported." While this is a valid design decision for performance, it means users on cloud instances without GPU, WSL without GPU passthrough, or CI environments cannot use any RAG features at all. A degraded CPU mode (slow but functional) would improve accessibility.
- **E3 - `store.py` module-level import of `EmbeddingModel`.** This means importing `rag.store` (even to check if the store exists) pulls in torch. If torch is installed but CUDA isn't available, this import succeeds but later operations crash.

### 6. pip Install Correctness

**Verdict: The install command works for the happy path but has multiple footguns.**

#### Happy path (works)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[rag,dev]" --extra-index-url https://download.pytorch.org/whl/cu130
```

This installs torch with CUDA 13.0 bindings, sentence-transformers, lancedb, einops, and dev tools.

#### Footguns

- **F1 - Bare `pip install -e ".[rag]"` installs CPU torch.** Without `--extra-index-url`, pip resolves `torch>=2.5.0` from PyPI, which is the CPU-only build. User gets `GPUNotAvailableError` at runtime with no indication of what went wrong.
- **F2 - `--index-url` vs `--extra-index-url` confusion.** With `torch>=2.10.0+cu130`, using `--index-url` fails because `cuda-bindings==13.0.3` isn't mirrored to the cu130 index. `--extra-index-url` is correct. README uses `--extra-index-url` (correct), but `_require_cuda()` error message says `--index-url` (incorrect).
- **F3 - No requirements.txt or lock file.** The only dependency spec is `pyproject.toml` optional-dependencies. There's no `requirements-rag.txt` or lock file that pins exact versions known to work together.
- **F4 - einops is listed but may not be needed.** The codebase doesn't directly import einops. It's a transitive dependency of nomic-embed-text-v1.5's `trust_remote_code=True` execution. This should be documented or the model should be loaded without `trust_remote_code`.

### 7. Online Research: Known Stack Issues

| Issue | Source | Impact |
|-------|--------|--------|
| GPU overclocking causes `CUBLAS_STATUS_EXECUTION_FAILED` with nomic-embed-text-v1.5 | [PyTorch Forums](https://discuss.pytorch.org/t/cuda-error-when-trying-to-run-nomic-embed-text-v1-5/206384) | Users with OC'd GPUs get cryptic errors |
| LanceDB float32 type errors in v0.18+ | [GitHub #2090](https://github.com/lancedb/lancedb/issues/2090) | Vector search fails silently |
| `torch.utils.data.DataLoader` with fork hangs Lance | [GitHub lance-format #2405](https://github.com/lance-format/lance/issues/2405) | Relevant if indexer ever uses DataLoader |
| `cuda-bindings==13.0.3` missing from cu130 index | [GitHub pytorch #172926](https://github.com/pytorch/pytorch/issues/172926) | `--index-url` installs fail for torch 2.10+ |
| nomic model requires compute capability >= 7.5 | [HuggingFace TEI docs](https://huggingface.co/docs/text-embeddings-inference/en/supported_models) | Pascal/Volta GPUs fail |

## Executive Summary

The RAG subsystem has **sound architecture** — lazy imports, proper exception hierarchy, graceful degradation for Tier 1 operations. However, the **dependency specification and documentation contain multiple inconsistencies** that will cause installation failures for most users:

- The CUDA 13.0 / cu130 requirement excludes the majority of current GPU setups (CUDA 12.x)
- The `torch>=2.5.0` floor contradicts the cu130 requirement (cu130 starts at torch 2.9.0)
- The hardcoded `cu124` URL in `_require_cuda()` contradicts the `cu130` in all docs
- Bare `pip install -e ".[rag]"` silently installs CPU torch
- No way to disable RAG via config when CUDA is unavailable but torch is installed
- `lancedb>=0.15.0` floor is far too low for the hybrid search features used

### Recommended decisions for ADR

- **Decision 1**: Lower CUDA floor to 12.1+ (or 11.8+) and make install docs version-agnostic, or raise torch floor to `>=2.9.0` to match cu130.
- **Decision 2**: Add `VAULTSPEC_RAG_ENABLED` env var to allow explicit disable.
- **Decision 3**: Fix the `_require_cuda()` error message to be dynamic (detect `torch.version.cuda` and suggest matching index URL).
- **Decision 4**: Raise `lancedb` floor to `>=0.20.0` minimum (for RRFReranker support).
- **Decision 5**: Add a `requirements-rag.txt` with pinned, tested versions.
- **Decision 6**: Decouple `store.py`'s module-level `EmbeddingModel` import from the constant it needs.

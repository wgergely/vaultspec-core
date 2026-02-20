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

Full audit of the CUDA dependency stack powering the RAG subsystem. The project mandates **Python 3.13+** and **CUDA 13.0+** as a deliberate frontier stance. This audit identifies where dependency floors, documentation, and in-code messages fail to align with that mandate.

## Findings

### 1. Documentation State

**Verdict: Documentation correctly states CUDA 13.0+ and Python 3.13+. The install URL and troubleshooting guidance are sound. Minor gaps remain.**

All documentation references **CUDA 13.0+** and the `cu130` index URL. CUDA 13.0 was released August 2025; CUDA 13.1 shipped December 2025. The cu130 PyTorch wheels are live on `download.pytorch.org`.

#### Files audited

| File | CUDA claim | Install command |
|------|-----------|-----------------|
| `README.md:44` | "CUDA 13.0+" | `pip install -e ".[rag,dev]" --extra-index-url https://download.pytorch.org/whl/cu130` |
| `docs/getting-started.md:9` | "CUDA 13.0+" | Same cu130 URL |
| `docs/getting-started.md:244` | Troubleshooting | `pip install torch --extra-index-url https://download.pytorch.org/whl/cu130` |
| `docs/search-guide.md:78` | "CUDA: 13.0+" | N/A |

#### Issues found

- **A1 - No mention of compute capability requirement.** The `nomic-embed-text-v1.5` model requires compute capability >= 7.5 (Turing or newer: RTX 2000+, T4+). Users with older GPUs (Pascal, Volta) will get cryptic CUDA errors. Docs should state this explicitly.
- **A2 - No `nvcc --version` vs `nvidia-smi` distinction.** Documentation tells users to run `nvidia-smi` to verify CUDA, but `nvidia-smi` shows the driver's CUDA compatibility version, not the toolkit version. This is a common source of confusion. Docs should mention both.
- **A3 - `pyproject.toml` dependency spec doesn't enforce the CUDA index.** The `[project.optional-dependencies] rag` section lists `torch>=2.5.0` without constraining the index URL. A bare `pip install -e ".[rag]"` pulls the CPU-only torch from PyPI, then the user gets `GPUNotAvailableError` at runtime. This is the **#1 installation footgun**. The torch floor must be raised to match the cu130 mandate.
- **A4 - `extension.toml` installs only `.[dev]`.** The runtime install command (`pip install -e '.[dev]'`) does not include `[rag]` extras. Users relying on extension-based installs will never get RAG deps.

### 2. In-Code Warning Messages

**Verdict: Good structure. The `_require_cuda()` error message is stale and must be updated to cu130.**

#### Warning/error inventory

| Location | Type | Message quality |
|----------|------|----------------|
| `embeddings.py:19-23` | `GPUNotAvailableError` class | Clear custom exception |
| `embeddings.py:25-33` | `_check_rag_deps()` | Clear: tells user to run `pip install -e '.[rag]'` |
| `embeddings.py:36-53` | `_require_cuda()` | **Stale**: hardcodes `cu124` in install hint |
| `embeddings.py:63-66` | `get_device_info()` | Calls both checks, good |
| `embeddings.py:112-114` | `EmbeddingModel.__init__` | Calls both checks, good |
| `api.py:107-132` | `get_engine()` | Calls `_require_cuda()`, catches exceptions, good |
| `api.py:206-208` | `get_document()` | Catches `ImportError` with debug log, good |
| `api.py:326-329` | `get_status()` | Catches `ImportError` and `FileNotFoundError`, good |
| `docs.py:119,145` | CLI epilog | "Requires NVIDIA GPU with CUDA" — adequate |
| `docs.py:374-376` | `handle_index` ImportError | "RAG dependencies not installed" — adequate |
| `docs.py:425-427` | `handle_search` ImportError | Same — adequate |

#### Issues found

- **B1 - `_require_cuda()` hardcodes `cu124`.** Line 52 says `pip install torch --index-url https://download.pytorch.org/whl/cu124`. Must be updated to `cu130` to match the project mandate. Should also use `--extra-index-url` (not `--index-url`) to avoid the `cuda-bindings` resolution bug.
- **B2 - `store.py:20` imports `EmbeddingModel` at module level.** This triggers the full torch import chain just to read `DEFAULT_DIMENSION = 768`. If torch isn't installed, importing `rag.store` fails even though the store itself only needs `lancedb`. The constant should be inlined or lazily resolved.

### 3. CUDA Version Audit

**Verdict: CUDA 13.0 mandate is correct. Dependency floors are far too low and must be raised to frontier versions.**

#### Current state vs required state

| Component | Current floor | Latest stable | Required floor | Rationale |
|-----------|--------------|---------------|----------------|-----------|
| CUDA Toolkit | 13.0+ (docs) | 13.1.1 (Jan 2026) | **13.0+** | Mandate — correct |
| PyTorch | `>=2.5.0` | 2.10.0 (Jan 2026) | **`>=2.9.0`** | cu130 wheels start at 2.9.0. torch 2.5 has no cu130 build. |
| sentence-transformers | `>=3.0.0` | 5.2 (Feb 2026) | **`>=5.0.0`** | 3.0 is 2+ years old. 5.x has Python 3.13 improvements and Transformers v5 support. |
| lancedb | `>=0.15.0` | 0.29.2 (Feb 2026) | **`>=0.27.0`** | 0.15 is ancient. RRFReranker, hybrid search stability, and float32 fixes landed in 0.20+. |
| einops | `>=0.7.0` | 0.8.1 | **`>=0.8.0`** | Minor bump for Python 3.13 compat. |
| Python | `>=3.13` (pyproject) | 3.13 | **`>=3.13`** | Mandate — correct |

#### Key issues

- **C1 - `torch>=2.5.0` is contradictory to the cu130 mandate.** There is no cu130 wheel for torch 2.5, 2.6, 2.7, or 2.8. The cu130 index starts at torch 2.9.0. A user on Python 3.13 literally cannot install torch 2.5.0 anyway (no wheel exists). The floor must be `>=2.9.0`.
- **C2 - `sentence-transformers>=3.0.0` is stale.** Version 3.0 predates Python 3.13 support in PyTorch. The current stable line is 5.x with Transformers v5 compatibility. Raise to `>=5.0.0`.
- **C3 - `lancedb>=0.15.0` is ancient.** The code uses `RRFReranker`, `create_fts_index(replace=True)`, and hybrid search patterns that stabilized in 0.20+. Version 0.15 may lack these or have float32 bugs ([GitHub #2090](https://github.com/lancedb/lancedb/issues/2090)). Raise to `>=0.27.0`.
- **C4 - `einops>=0.7.0` should be `>=0.8.0`.** Minor bump to stay current.

### 4. Python Version Audit

**Verdict: Python 3.13 mandate is correct. All dependencies support it when floors are raised.**

| Component | Python 3.13 support |
|-----------|-------------------|
| PyTorch >= 2.9.0 | Fully supported (since 2.6, Jan 2025) |
| sentence-transformers >= 5.0.0 | Supported (requires PyTorch with 3.13 support) |
| lancedb >= 0.27.0 | Supported (stable ABI `cp39-abi3`) |
| einops >= 0.8.0 | Pure Python, fully supported |

The Python 3.13 mandate is self-consistent **once the torch floor is raised to >=2.9.0**. With the current `torch>=2.5.0`, there is no Python 3.13 wheel for torch 2.5, making the spec unsatisfiable in edge cases where pip resolves to an old torch version.

### 5. Graceful Degradation / Disconnect

**Verdict: RAG correctly disables when deps are missing. GPU absence is a deliberate hard fatal — this is the correct design for a CUDA 13 mandate.**

#### What works

- Tier 1 functions (`list_documents`, `get_document` filesystem fallback, `get_related`, `get_status`) work without RAG deps via `ImportError` catches.
- `get_document()` falls back to filesystem scan when vector store lookup fails.
- `get_status()` returns `index.exists=False` and `index.device=None` when RAG is unavailable.
- Tests use `pytest.mark.skipif(not HAS_RAG, ...)` to skip RAG tests cleanly.
- CLI commands (`docs.py index`, `docs.py search`) catch `ImportError` and print actionable install instructions.

#### What should be improved

- **E1 - `GPUNotAvailableError` message should reference CUDA 13.0 mandate.** The current message is generic. It should clearly state that vaultspec requires CUDA 13.0+ and point users to the correct install URL.
- **E2 - `store.py` module-level import of `EmbeddingModel`.** Importing `rag.store` (even to check if the store exists) pulls in torch. If torch is installed but CUDA isn't available, this import succeeds but later operations crash. The `EMBEDDING_DIM = EmbeddingModel.DEFAULT_DIMENSION` constant should be inlined as `EMBEDDING_DIM = 768` to decouple the store from the embedding model at import time.
- **E3 - Consider a `VAULTSPEC_RAG_ENABLED=false` config override.** For CI environments or development machines where torch is installed (as a transitive dep of other tools) but no GPU is present, a config-level disable would prevent `GPUNotAvailableError` from crashing unrelated operations.

### 6. pip Install Correctness

**Verdict: The happy-path install works. The bare install path is a footgun. No lock file exists.**

#### Happy path (works)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[rag,dev]" --extra-index-url https://download.pytorch.org/whl/cu130
```

#### Footguns

- **F1 - Bare `pip install -e ".[rag]"` installs CPU torch.** Without `--extra-index-url`, pip resolves torch from PyPI (CPU-only build). User gets `GPUNotAvailableError` at runtime with no indication of what went wrong. The documentation must make the `--extra-index-url` requirement unmissable.
- **F2 - `--index-url` vs `--extra-index-url`.** The `_require_cuda()` error message says `--index-url`. For torch 2.10+, using `--index-url` fails because `cuda-bindings==13.0.3` isn't mirrored to the cu130 index ([GitHub pytorch #172926](https://github.com/pytorch/pytorch/issues/172926)). `--extra-index-url` is the correct flag. All references must use `--extra-index-url`.
- **F3 - No requirements lock file.** The only dependency spec is `pyproject.toml` optional-dependencies. A `requirements-rag.txt` with pinned, tested versions would prevent version drift from breaking installs.
- **F4 - einops is an implicit dependency.** The codebase doesn't import einops directly. It's a transitive dependency of `nomic-embed-text-v1.5` via `trust_remote_code=True`. This should be documented in a comment in pyproject.toml.

### 7. Online Research: Known Stack Issues

| Issue | Source | Impact |
|-------|--------|--------|
| GPU overclocking causes `CUBLAS_STATUS_EXECUTION_FAILED` with nomic-embed-text-v1.5 | [PyTorch Forums](https://discuss.pytorch.org/t/cuda-error-when-trying-to-run-nomic-embed-text-v1-5/206384) | Users with OC'd GPUs get cryptic errors |
| LanceDB float32 type errors in v0.18+ | [GitHub #2090](https://github.com/lancedb/lancedb/issues/2090) | Fixed in later versions — raising floor avoids this |
| `torch.utils.data.DataLoader` with fork hangs Lance | [GitHub lance-format #2405](https://github.com/lance-format/lance/issues/2405) | Relevant if indexer ever uses DataLoader |
| `cuda-bindings==13.0.3` missing from cu130 index | [GitHub pytorch #172926](https://github.com/pytorch/pytorch/issues/172926) | Must use `--extra-index-url` not `--index-url` |
| nomic model requires compute capability >= 7.5 | [HuggingFace TEI docs](https://huggingface.co/docs/text-embeddings-inference/en/supported_models) | Pascal/Volta GPUs fail — should be documented |

## Executive Summary

The project's **CUDA 13.0+ and Python 3.13+ mandates are correct and deliberate**. The frontier stance is sound — all dependencies support this stack when properly versioned. The core problem is that **dependency floors in `pyproject.toml` are stale** and lag far behind the mandate:

- `torch>=2.5.0` has no cu130 wheel — must be `>=2.9.0`
- `sentence-transformers>=3.0.0` is 2+ years old — must be `>=5.0.0`
- `lancedb>=0.15.0` is ancient and may lack features used — must be `>=0.27.0`
- `einops>=0.7.0` should be `>=0.8.0`

Secondary issues:

- `_require_cuda()` error message hardcodes stale `cu124` URL — must say `cu130`
- `_require_cuda()` uses `--index-url` — must use `--extra-index-url`
- `store.py` module-level import of `EmbeddingModel` is unnecessary coupling
- Documentation should mention compute capability >= 7.5 and the `nvcc`/`nvidia-smi` distinction

### Recommended decisions for ADR

- **Decision 1**: Raise all dependency floors to frontier versions (`torch>=2.9.0`, `sentence-transformers>=5.0.0`, `lancedb>=0.27.0`, `einops>=0.8.0`).
- **Decision 2**: Fix `_require_cuda()` to reference `cu130` and use `--extra-index-url`.
- **Decision 3**: Decouple `store.py` module-level import — inline `EMBEDDING_DIM = 768`.
- **Decision 4**: Add compute capability >= 7.5 requirement to docs.
- **Decision 5**: Add `--extra-index-url` warning to all install instructions to prevent the CPU-torch footgun.
- **Decision 6**: Consider adding `VAULTSPEC_RAG_ENABLED` config override for GPU-less environments.

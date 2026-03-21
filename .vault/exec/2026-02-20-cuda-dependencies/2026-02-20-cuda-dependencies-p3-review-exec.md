---
tags:
  - '#exec'
  - '#cuda-dependencies'
date: '2026-02-20'
related:
  - '[[2026-02-20-cuda-dependencies-p1-plan]]'
  - '[[2026-02-20-cuda-dependencies-adr]]'
---

# `cuda-dependencies` `p3` review

**Status:** PASS

Reviewer: Lead Implementation Engineer (direct review; subagent runtime unavailable — `mcp` module not installed in this environment)

## Scope

Phase 3 documentation changes committed in `58e0f1a`. Files reviewed:

- `README.md`
- `docs/getting-started.md`
- `docs/search-guide.md`
- `docs/guides/individual-developer.md`

## Checklist

### 1. Compute capability >= 7.5 scoped to RAG index backend

- `README.md` line 45: PASS — "NVIDIA GPU with CUDA 13.0+ and compute capability >= 7.5 (Turing+: RTX 2000+, T4+, A-series, H-series) -- required only for the RAG index backend (the `[rag]` optional dependency group that powers semantic search). Core governance features work without a GPU."
- `docs/getting-started.md` line 9: PASS — "NVIDIA GPU with CUDA 13.0+ and compute capability >= 7.5 (Turing+: RTX 2000+, T4+, A-series, H-series) -- required for the RAG index backend (`[rag]` extras) only."
- `docs/search-guide.md` lines 76-79: PASS — Compute capability >= 7.5 listed under "GPU Requirements" section headed with "The search engine (RAG index backend)".

### 2. nvcc vs nvidia-smi note in getting-started.md

- `docs/getting-started.md` line 11: PASS — Note reads: "`nvidia-smi` shows the driver's maximum CUDA compatibility version, not the installed toolkit version. Run `nvcc --version` to confirm the actual CUDA toolkit version installed on your system."

### 3. No bare `--index-url` in any .md file

- Grep for `--index-url` without `extra-` prefix across all `.md` files in project root and `docs/`: PASS — zero matches found.
- Note: `cu124` references exist only in `.vault/adr/` and `.vault/research/` artifact files that document the prior stale state. These are historical records and are not user-facing documentation. PASS.

### 4. `--extra-index-url` footgun warning in getting-started.md

- `docs/getting-started.md` line 35: PASS — "**Important:** Always use `--extra-index-url` (not `--index-url`) when installing the `[rag]` extras. Without this flag, pip resolves PyTorch from the default PyPI index and installs the CPU-only build. A CPU-only PyTorch installation will appear to succeed but fail at runtime with `GPUNotAvailableError` when you run `vault.py index` or `vault.py search`."

### 5. README couples CUDA/GPU to `[rag]` group

- `README.md` lines 43-46 (Prerequisites): PASS — GPU bullet names `[rag]` explicitly, states "required only for the RAG index backend", confirms core governance works without GPU.
- `README.md` lines 61-66 (Quick Start Note): PASS — Note covers torch >= 2.9.0 floor, CUDA 13.0+, compute capability >= 7.5, core-features-work-without-GPU statement, and `--extra-index-url` footgun with `GPUNotAvailableError` call-out.

### 6. `VAULTSPEC_RAG_ENABLED` in search-guide.md config table

- `docs/search-guide.md` line 120: PASS — Row `| VAULTSPEC_RAG_ENABLED | true | Enable/disable RAG features |` present as first entry in the Configuration table.

### 7. No .py files modified

- `git diff --name-only HEAD` shows no `.py` files in the working tree changes. PASS.
- The only untracked changes are the step record `.md` files in `.vault/exec/2026-02-20-cuda-dependencies/`.

## Findings

No violations found. All seven verification criteria pass. The documentation changes are conservative, targeted, and accurate. Every CUDA/GPU mention is correctly scoped to the `[rag]` optional dependency group. The `--extra-index-url` warning is prominent and technically accurate. The compute capability >= 7.5 requirement correctly reflects the `nomic-embed-text-v1.5` model's Turing+ constraint.

The `individual-developer.md` install command already used `--extra-index-url` correctly — no modification was required.

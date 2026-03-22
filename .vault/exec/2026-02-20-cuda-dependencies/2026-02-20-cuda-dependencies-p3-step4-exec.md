---
tags:
  - '#exec'
  - '#cuda-dependencies'
date: '2026-02-20'
related:
  - '[[2026-02-20-cuda-dependencies-p1-plan]]'
---

# `cuda-dependencies` `p3` `step4`

Strengthened README Prerequisites section and Quick Start note to explicitly couple all CUDA/GPU requirements with the RAG index backend.

- Modified: `[[README]]`

## Description

### Prerequisites section (lines 41-46)

Rewrote the GPU bullet to make the scope unambiguous:

```markdown

- **NVIDIA GPU** with CUDA 13.0+ and compute capability >= 7.5 (Turing+: RTX 2000+, T4+, A-series, H-series) -- required only for the RAG index backend (the `[rag]` optional dependency group that powers semantic search). Core governance features (Research → Specify → Plan → Execute → Verify) work without a GPU.
```

Key changes from the prior "NVIDIA GPU with CUDA 13.0+ (required for RAG/search features)" wording:

- Added compute capability >= 7.5 with specific GPU family examples (Turing+: RTX 2000+, T4+, A-series, H-series)
- Named the `[rag]` optional dependency group explicitly as the scope boundary
- Clarified "semantic search" as the specific capability powered by GPU
- Added the explicit statement that core governance features work without a GPU

### Quick Start note (lines 61-66)

Expanded the `> **Note:**` block to serve as the authoritative first-contact explanation:

```markdown
> **Note:** The `[rag]` optional dependency group powers the semantic search index
> (torch >= 2.9.0, CUDA 13.0+, compute capability >= 7.5). Core governance features
> (Research → Specify → Plan → Execute → Verify) work without a GPU — omit `[rag]`
> and skip the `vault.py index` step. Always use `--extra-index-url` (not `--index-url`)
> when installing `[rag]` dependencies: without it, pip installs CPU-only PyTorch from
> PyPI, which fails at runtime with `GPUNotAvailableError`.
```

This note now covers all four requirements from the plan:

- Explicit `[rag]` scoping with raised dependency floors (torch >= 2.9.0, CUDA 13.0+)
- Compute capability >= 7.5
- Core governance works without GPU
- `--extra-index-url` footgun warning with the specific error name (`GPUNotAvailableError`)

## Tests

No automated tests. Verified by reading `README.md` lines 41-66 and confirming all required content is present.

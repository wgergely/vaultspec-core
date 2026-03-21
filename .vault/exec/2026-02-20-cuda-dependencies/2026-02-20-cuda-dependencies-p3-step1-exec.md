---
tags:
  - "#exec"
  - "#cuda-dependencies"
date: "2026-02-20"
related:
  - "[[2026-02-20-cuda-dependencies-p1-plan]]"
---
# `cuda-dependencies` `p3` `step1`

Added compute capability >= 7.5 (Turing+) requirement to prerequisites sections, scoped to the RAG index backend.

- Modified: `[[README]]`
- Modified: `[[docs/getting-started]]`
- Modified: `[[docs/search-guide]]`

## Description

Each prerequisites section now explicitly states the NVIDIA GPU compute capability >= 7.5 (Turing+: RTX 2000+, T4+, A-series, H-series) requirement and scopes it to the RAG index backend / `[rag]` optional dependency group:

- `README.md` line 45: Updated bullet to read "NVIDIA GPU with CUDA 13.0+ and compute capability >= 7.5 (Turing+: RTX 2000+, T4+, A-series, H-series) -- required only for the RAG index backend (the `[rag]` optional dependency group that powers semantic search). Core governance features work without a GPU."
- `docs/getting-started.md` line 9: Updated bullet to read "NVIDIA GPU with CUDA 13.0+ and compute capability >= 7.5 (Turing+: RTX 2000+, T4+, A-series, H-series) -- required for the RAG index backend (`[rag]` extras) only."
- `docs/search-guide.md` GPU Requirements section (lines 76-83): Retained existing compute capability >= 7.5 entry in the bulleted list under the RAG index backend heading.

## Tests

No automated tests. Verified by reading all three files and confirming the compute capability language is present and correctly scoped.

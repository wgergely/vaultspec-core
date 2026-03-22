---
tags:
  - '#exec'
  - '#cuda-dependencies'
date: '2026-02-20'
related:
  - '[[2026-02-20-cuda-dependencies-p1-plan]]'
---

# `cuda-dependencies` `p1` `step1`

Added centralized CUDA index constants to `embeddings.py`.

- Modified: `[[embeddings.py]]`

## Description

Defined `CUDA_INDEX_TAG = "cu130"` and `CUDA_INDEX_URL` (derived from the tag) as
module-level constants in `rag/embeddings.py`, placed after the logger and before
`GPUNotAvailableError`. These constants serve as the single source of truth for the
CUDA wheel identifier, consumed by the error message in `_require_cuda()` and
available for any future references.

## Tests

No tests required for constant definitions. Verified file parses correctly.

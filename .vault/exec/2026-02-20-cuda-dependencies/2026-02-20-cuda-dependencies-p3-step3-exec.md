---
tags:
  - '#exec'
  - '#cuda-dependencies'
date: '2026-02-20'
related:
  - '[[2026-02-20-cuda-dependencies-p1-plan]]'
---

# `cuda-dependencies` `p3` `step3`

Standardized `--extra-index-url` across all install references in documentation and added a prominent warning callout in `docs/getting-started.md`.

- Modified: `[[README]]`
- Modified: `[[docs/getting-started]]`
- Modified: `[[docs/search-guide]]`
- Modified: `[[docs/guides/individual-developer]]`

## Description

Audited all four target files for bare `--index-url` (without the `extra-` prefix) occurrences. All install command references already used `--extra-index-url https://download.pytorch.org/whl/cu130`. No replacement was required for any of the four files on the `--index-url` → `--extra-index-url` fix.

Added a prominent warning callout in `docs/getting-started.md` (line 35) immediately after the install command block:

> **Important:** Always use `--extra-index-url` (not `--index-url`) when installing the `[rag]` extras. Without this flag, pip resolves PyTorch from the default PyPI index and installs the CPU-only build. A CPU-only PyTorch installation will appear to succeed but fail at runtime with `GPUNotAvailableError` when you run `vault.py index` or `vault.py search`.

The rationale: using `--index-url` (without `extra-`) for torch 2.10+ fails because `cuda-bindings==13.0.3` is not mirrored to the PyTorch cu130 index (see pytorch/pytorch#172926). `--extra-index-url` preserves the PyPI index fallback for all other packages while directing torch resolution to the CUDA wheel index.

## Tests

No automated tests. Verified by grepping all four files for `--index-url` patterns, confirming zero bare `--index-url` occurrences and the Important callout is present in `docs/getting-started.md`.

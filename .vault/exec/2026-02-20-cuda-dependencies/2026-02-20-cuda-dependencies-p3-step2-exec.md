---
tags:
  - "#exec"
  - "#cuda-dependencies"
date: "2026-02-20"
related:
  - "[[2026-02-20-cuda-dependencies-p1-plan]]"
---
# `cuda-dependencies` `p3` `step2`

Added clarifying note about `nvidia-smi` vs `nvcc --version` to `docs/getting-started.md`.

- Modified: `[[docs/getting-started.md]]`

## Description

In the Prerequisites section of `docs/getting-started.md`, immediately after the `nvidia-smi` verification instruction on line 9, added a nested note (line 11):

> **Note:** `nvidia-smi` shows the driver's maximum CUDA compatibility version, not the installed toolkit version. Run `nvcc --version` to confirm the actual CUDA toolkit version installed on your system.

This addresses a common source of confusion: `nvidia-smi` reports the driver's highest CUDA API compatibility level (e.g., "CUDA Version: 13.0"), which does not mean CUDA 13.0 toolkit is actually installed. Users must verify the toolkit with `nvcc --version` to confirm vaultspec's CUDA 13.0+ mandate is met at the toolkit level.

## Tests

No automated tests. Verified by reading `docs/getting-started.md` lines 9-12 and confirming the note is present directly after the `nvidia-smi` reference.

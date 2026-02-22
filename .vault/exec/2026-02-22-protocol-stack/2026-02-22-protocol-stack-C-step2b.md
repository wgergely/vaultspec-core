---
tags:
  - "#exec"
  - "#protocol-stack"
date: "2026-02-22"
related:
  - "[[2026-02-22-protocol-stack-deep-audit-plan]]"
---

# `protocol-stack` Track C `Step 2b`

Fixed stale `MODULE_PATHS` in `cli.py` that referenced pre-restructure paths.

- Modified: `src/vaultspec/cli.py`

## Description

Replaced all `.vaultspec/lib/tests/` and `.vaultspec/lib/src/` paths with
correct post-restructure paths under `src/vaultspec/`. Added `core` and
`mcp_tools` modules. Updated fallback `else` branch from
`.vaultspec/lib/tests` + `.vaultspec/lib/src` to `src/vaultspec` + `tests/`.

Verified actual test directory layout via Glob — all 13 test `__init__.py`
files confirmed under `src/vaultspec/**/tests/`.

## Tests

`vaultspec test` will now discover tests in the correct directories.

---
tags:
  - '#exec'
  - '#cuda-dependencies'
date: '2026-02-20'
related:
  - '[[2026-02-20-cuda-dependencies-p1-plan]]'
---

# `cuda-dependencies` `p3` `step5`

Added `VAULTSPEC_RAG_ENABLED` entry to the Configuration table in `docs/search-guide.md`.

- Modified: `[[docs/search-guide]]`

## Description

Added a new row to the Configuration environment variable table in the "Configuration" section of `docs/search-guide.md` (line 120):

```markdown
| `VAULTSPEC_RAG_ENABLED` | `true` | Enable/disable RAG features |
```

This entry is placed as the first row in the table, above `VAULTSPEC_EMBEDDING_MODEL`, reflecting its role as the top-level feature gate. It documents the new config variable introduced in Phase 1 Step 2 (`VAULTSPEC_RAG_ENABLED` added to `core/config.py` CONFIG_REGISTRY and `VaultSpecConfig` dataclass).

The variable allows users in GPU-less environments to explicitly opt out of RAG at configuration level rather than receiving a runtime `GPUNotAvailableError`. Setting `VAULTSPEC_RAG_ENABLED=false` causes `get_engine()` to raise `ImportError("RAG disabled by configuration")` which triggers the existing Tier 1 fallback paths.

## Tests

No automated tests. Verified by reading `docs/search-guide.md` lines 118-126 and confirming the `VAULTSPEC_RAG_ENABLED` row is present in the table with correct default value and description.

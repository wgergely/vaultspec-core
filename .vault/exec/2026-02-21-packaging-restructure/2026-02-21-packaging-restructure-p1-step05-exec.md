---
tags:
  - '#exec'
  - '#packaging-restructure'
date: '2026-02-21'
related:
  - '[[2026-02-21-packaging-restructure-p1p2-plan]]'
---

# Step 5: Rewrite imports in leaf packages `core/` and `vaultcore/`

## Status: COMPLETE

## Summary

Rewrote all bare-name imports in `src/vaultspec/core/` and `src/vaultspec/vaultcore/` (production and test files) to use `vaultspec.*` prefixed forms.

## Files Modified

- `src/vaultspec/core/tests/test_workspace.py` -- `from core.workspace` -> `from vaultspec.core.workspace`
- `src/vaultspec/core/tests/test_config.py` -- `from core.config` -> `from vaultspec.core.config`
- `src/vaultspec/vaultcore/parser.py` -- `from vaultcore.models` -> `from vaultspec.vaultcore.models`
- `src/vaultspec/vaultcore/scanner.py` -- `from vaultcore.models` -> `from vaultspec.vaultcore.models`; two deferred `from core.config` -> `from vaultspec.core.config`
- `src/vaultspec/vaultcore/hydration.py` -- `from vaultcore.models` -> `from vaultspec.vaultcore.models`; deferred `from core.config` -> `from vaultspec.core.config`
- `src/vaultspec/vaultcore/tests/test_core.py` -- `from vaultcore.parser` -> `from vaultspec.vaultcore.parser`; `from protocol.providers.base` -> `from vaultspec.protocol.providers.base`
- `src/vaultspec/vaultcore/tests/test_links.py` -- `from vaultcore.links` -> `from vaultspec.vaultcore.links`
- `src/vaultspec/vaultcore/tests/test_scanner.py` -- `from core.config` -> `from vaultspec.core.config`; `from vaultcore.*` -> `from vaultspec.vaultcore.*`
- `src/vaultspec/vaultcore/tests/test_types.py` -- `from vaultcore.*` -> `from vaultspec.vaultcore.*`
- `src/vaultspec/vaultcore/tests/test_hydration.py` -- `from vaultcore.*` -> `from vaultspec.vaultcore.*`

## Verification

Grep scan of both directories confirms zero bare-name imports remain.

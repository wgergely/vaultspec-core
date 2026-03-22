---
tags:
  - '#exec'
  - '#check-engine-perf'
date: '2026-03-21'
related:
  - '[[2026-03-21-check-engine-perf-plan]]'
---

# check-engine-perf summary

Shared VaultGraph and VaultSnapshot across all checkers, reducing I/O from 7N to 1N file reads per `run_all_checks` invocation.

- Modified: `src/vaultspec_core/vaultcore/checks/__init__.py`
- Modified: `src/vaultspec_core/vaultcore/checks/_base.py`
- Modified: `src/vaultspec_core/vaultcore/checks/orphans.py`
- Modified: `src/vaultspec_core/vaultcore/checks/references.py`
- Modified: `src/vaultspec_core/vaultcore/checks/structure.py`
- Modified: `src/vaultspec_core/vaultcore/checks/frontmatter.py`
- Modified: `src/vaultspec_core/vaultcore/checks/links.py`
- Modified: `src/vaultspec_core/vaultcore/checks/features.py`
- Modified: `src/vaultspec_core/graph/api.py`
- Modified: `src/vaultspec_core/cli/vault_cmd.py`

## Description

- Defined `VaultDocData` and `VaultSnapshot` types in `_base.py`
- Added `to_snapshot()` method on `VaultGraph`
- Changed all 7 checkers to accept required `graph` or `snapshot` parameters
- `run_all_checks` builds one graph, derives one snapshot, passes to all
- CLI call sites construct graph/snapshot at invocation
- Deleted `_scan_all` from `check_features`

## Tests

757 tests pass. No regressions. All check behavior identical before and after.

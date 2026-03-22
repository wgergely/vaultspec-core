---
tags:
  - '#exec'
  - '#check-engine-perf'
date: '2026-03-21'
related:
  - '[[2026-03-21-check-engine-perf-plan]]'
---

# check-engine-perf task-1 task-2

Refactored graph-consuming checkers to accept a shared `VaultGraph` and
defined the `VaultSnapshot` type with a `to_snapshot()` extraction method.

- Modified: `src/vaultspec_core/vaultcore/checks/orphans.py`
- Modified: `src/vaultspec_core/vaultcore/checks/references.py`
- Modified: `src/vaultspec_core/vaultcore/checks/__init__.py`
- Modified: `src/vaultspec_core/vaultcore/checks/_base.py`
- Modified: `src/vaultspec_core/graph/api.py`
- Modified: `src/vaultspec_core/cli/vault_cmd.py`

## Description

**Task 1 - required `graph` parameter:** Changed `check_orphans`,
`check_references`, and `check_schema` signatures to accept a required
`graph: VaultGraph` parameter. Removed internal `VaultGraph(root_dir)`
construction from each checker. Moved the `VaultGraph` import from a lazy
in-function import to a top-level import in both `orphans.py` and
`references.py`. Updated `run_all_checks` to build a single `VaultGraph`
and pass it to all three graph-consuming checkers. Updated the three
standalone CLI call sites (`cmd_check_orphans`, `cmd_check_references`,
`cmd_check_schema`) to construct the graph at the call site.

**Task 2 - VaultSnapshot type and extraction:** Defined `VaultDocData`
(a `tuple[DocumentMetadata, str]`) and `VaultSnapshot`
(a `dict[Path, VaultDocData]`) in `checks/_base.py`. Added a
`to_snapshot()` method on `VaultGraph` that iterates all nodes and builds
a `DocumentMetadata` from each node's tags, date, and related frontmatter,
paired with the node body. Exported both types from `checks/__init__.py`.

## Tests

All 137 existing tests in `vaultcore/tests/` and `graph/tests/` pass
without modification, confirming backward compatibility of the signature
changes and the new `to_snapshot()` method.

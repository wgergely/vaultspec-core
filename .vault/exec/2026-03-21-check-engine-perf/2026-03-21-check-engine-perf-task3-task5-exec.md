---
tags:
  - '#exec'
  - '#check-engine-perf'
date: '2026-03-21'
related:
  - '[[2026-03-21-check-engine-perf-plan]]'
---

# check-engine-perf task3-task5

Migrated all four non-graph checkers to accept a required `snapshot` parameter,
updated `run_all_checks` to derive the snapshot from the shared graph, and
updated all standalone CLI call sites to construct graph/snapshot before
invoking checkers.

- Modified: `structure.py` - replaced `scan_vault()` iteration with `snapshot` keys
- Modified: `frontmatter.py` - replaced `scan_vault()` + `read_text()` with snapshot data
- Modified: `links.py` - replaced `scan_vault()` + `read_text()` with snapshot body/related
- Modified: `features.py` - replaced `_scan_all()` with snapshot iteration, removed query import
- Modified: `__init__.py` - `run_all_checks` now calls `graph.to_snapshot()` and passes it
- Modified: `vault_cmd.py` - four CLI commands construct graph/snapshot at call site
- Fixed: `api.py` - `to_snapshot()` now filters non-string related items

## Description

**Task 3:** Each of the four non-graph checkers (`check_structure`,
`check_frontmatter`, `check_links`, `check_features`) gained a required
`snapshot: VaultSnapshot` parameter. Internal `scan_vault()` calls and
`path.read_text()` reads were removed in favour of iterating
`snapshot.items()` or `snapshot.keys()`. The `check_features` function no
longer imports `_scan_all` from the query module; it derives feature-to-doctype
mappings directly from snapshot metadata via `extract_feature_tags` and
`get_doc_type`.

For `check_links` and `check_frontmatter`, fix-mode still performs targeted
file I/O (read-modify-write) since the snapshot is read-only.

**Task 4:** `run_all_checks` now calls `graph.to_snapshot()` immediately after
constructing the `VaultGraph` and passes `snapshot=snapshot` to all four
non-graph checkers alongside the existing `graph=graph` for graph-consuming
checkers.

**Task 5:** The four standalone CLI commands (`cmd_check_frontmatter`,
`cmd_check_links`, `cmd_check_structure`, `cmd_check_features`) now construct a
`VaultGraph` and derive a snapshot at the call site, matching the pattern
already established by `cmd_check_orphans`, `cmd_check_references`, and
`cmd_check_schema`.

A data integrity fix was also applied to `to_snapshot()`: the `related` field
from `node.frontmatter` (raw YAML parse) could contain non-string items, which
caused `AttributeError` in `DocumentMetadata.validate()`. The fix filters
related items to strings only.

## Tests

All 560 tests pass across `vaultcore/tests/`, `graph/tests/`, and `tests/cli/`.
The previously failing `TestPathsEnvBridge::test_target_override` was fixed by
the `to_snapshot()` related-field sanitisation.

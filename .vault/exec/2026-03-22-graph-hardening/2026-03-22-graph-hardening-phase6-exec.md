---
tags:
  - '#exec'
  - '#graph-hardening'
date: '2026-03-22'
related:
  - '[[2026-03-22-graph-hardening-plan]]'
---

# graph-hardening phase 6 - tests

## Scope

Add comprehensive test coverage for phantom node behaviour, phantom-aware
guards, rendering, JSON output, and the new `check_dangling` checker.

## Changes

### `src/vaultspec_core/graph/tests/test_graph.py`

Added 13 new tests across two new test classes:

- **TestDocNodePhantom** (3 tests)

  - `test_defaults_include_phantom_false` - DocNode defaults phantom to False
  - `test_to_nx_attrs_includes_phantom_field` - phantom field in nx attrs dict
  - `test_to_nx_attrs_phantom_true` - phantom=True serialises correctly

- **TestVaultGraphPhantom** (10 tests)

  - `test_builds_many_nodes_includes_phantoms` - total count = real + phantom
  - `test_phantom_nodes_created_for_unresolved_targets` - phantom=True, in graph.nodes, in digraph
  - `test_phantom_nodes_have_incoming_edges` - every phantom has in_links with real digraph edges
  - `test_get_orphaned_excludes_phantoms` - no phantom names in orphan list
  - `test_to_snapshot_excludes_phantoms` - no phantom path keys in snapshot
  - `test_metrics_phantom_count` - metrics().phantom_count matches actual count
  - `test_metrics_invalid_link_count` - equals edge count to phantom targets
  - `test_check_schema_ignores_phantom_adr_references` - plan linking only to phantom ADR still reports error
  - `test_tree_rendering_shows_not_created_for_phantoms` - "(not created)" in tree output
  - `test_json_output_includes_phantom_flag` - phantom: true in JSON node dicts

### `src/vaultspec_core/vaultcore/checks/tests/` (new directory)

- **conftest.py** - vault_root fixture pointing to test-project, config reset
- **__init__.py** - package marker
- **test_dangling.py** - TestCheckDangling (2 tests)
  - `test_reports_error_for_each_dangling_link` - ERROR severity, count matches invalid links
  - `test_fix_removes_related_entry` - copies vault to tmp, runs fix, verifies entry removed

## Results

- 66 graph tests passed (53 existing + 13 new)
- 2 dangling checker tests passed
- All ruff checks clean, all ty checks clean
- Full suite: 749 passed, 6 deselected (4m16s)

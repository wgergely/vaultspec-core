---
tags:
  - '#exec'
  - '#graph-hardening'
date: '2026-03-22'
related:
  - '[[2026-03-22-graph-hardening-plan]]'
---

# graph-hardening phase3 - rendering

Phase 3 updates tree rendering, JSON serialization, and CLI metrics output
to surface phantom nodes distinctly.

## Changes

### `_add_typed_nodes()` in `api.py`

- Phantom link targets now render with `(not created)` label styled in
  yellow italic, replacing the old `(broken)` red label.
- Check order: phantom first, then real node, then fallback `(broken)` for
  defensive coverage if a target is somehow missing from `self.nodes`.
- Phantom nodes render inline under their referencing node (as outgoing
  link targets), not as standalone tree entries - this is the existing
  behavior since `get_feature_nodes()` excludes phantoms.

### `to_dict()` / JSON serialization

- No code changes needed. Phantom nodes already carry `phantom: true` in
  their nx attrs from Phase 1's `to_nx_attrs()`. Body is always empty
  string for phantoms. Verified: full graph JSON export includes phantom
  nodes with `phantom: true` flag and empty body.
- Feature-scoped subgraphs correctly exclude phantom nodes from the node
  list (phantoms have no feature tag), while real nodes still show phantom
  targets in their `out_links`.

### `_print_metrics()` in `vault_cmd.py`

- Added `Phantoms` row between `Orphans` and `Invalid links` in the
  metrics table, displaying `GraphMetrics.phantom_count`.

## Files Modified

- `src/vaultspec_core/graph/api.py` - `_add_typed_nodes()` method
- `src/vaultspec_core/cli/vault_cmd.py` - `_print_metrics()` function

## Verification

- `ruff check` - all checks passed
- `ruff format` - 2 files unchanged
- `ty check` - all checks passed
- `pytest test_graph.py` - 53 passed
- `vault graph --feature claude-a2a-overhaul` - shows `(not created)` for
  phantom targets (e.g. `2026-02-22-claude-team-management-adr`)
- `vault graph --metrics` - shows `Phantoms: 93`, `Invalid links: 156`
- JSON export includes `phantom: true` on phantom node dicts with empty
  body confirmed via Python API

---
tags:
  - '#audit'
  - '#graph-hardening'
date: '2026-03-22'
related:
  - '[[2026-03-22-graph-hardening-plan]]'
  - '[[2026-03-22-graph-hardening-phase1-exec]]'
---

# `graph-hardening` code review - phase 1

- api.py-001 | HIGH | **FIXED** - Phantom nodes leaked into `render_tree()` untagged section. Added `not n.phantom` guard.
- api.py-002 | MEDIUM | `metrics()` counts phantoms under `"unknown"` in `nodes_by_type` and inflates `total_nodes`. Deferred to Phase 2 (`phantom_count` field).
- api.py-003 | MEDIUM | `get_hotspots()` includes phantom nodes in rankings. Deferred to Phase 2 guard.
- api.py-004 | LOW | `get_invalid_links()` docstring says "target does not exist as a node" but phantoms now exist as nodes. Docstring update needed.
- api.py-005 | LOW | `_resolve_link()` docstring doesn't mention phantom matching. Cosmetic.
- test-001 | MEDIUM | `test_builds_many_nodes` inflated by phantom count. Phase 6 scope.
- test-002 | MEDIUM | `test_get_invalid_links` has no meaningful assertion. Phase 6 scope.
- test-003 | LOW | `test_defaults` and `test_to_nx_attrs_includes_all_fields` don't cover `phantom` field. Phase 6 scope.

---
tags:
  - '#exec'
  - '#graph-hardening'
date: '2026-03-22'
related:
  - '[[2026-03-22-graph-hardening-plan]]'
---

# `graph-hardening` phase 1: phantom nodes in the graph

- Modified: `src/vaultspec_core/graph/api.py`
- Modified: `src/vaultspec_core/graph/tests/test_graph.py`

## Description

Added phantom node support to the vault graph, mirroring Obsidian's
"not created" link model. Changes to `api.py`:

- `DocNode.path` type widened to `pathlib.Path | None` for phantoms.
- `DocNode.phantom: bool = False` field added.
- `to_nx_attrs()` includes `phantom` flag and handles `None` path.
- `_build_graph()` pass 2 creates phantom `DocNode` instances for
  unresolved wiki-link targets. Real DiGraph edges connect sources to
  phantoms. Deduplication is natural: once a phantom is in `self.nodes`,
  subsequent references resolve to it via `_resolve_link()`.
- `_invalid_links` records every edge to a phantom (not just first
  discovery), so the count matches total edges to phantom targets.
- `to_snapshot()` excludes phantom nodes (no file to lint).
- `get_orphaned()` excludes phantom nodes.

Test fix: `test_no_nodes_lost_to_stem_collisions` now filters phantoms
when comparing against `scan_vault()` file count.

## Tests

- 53 graph tests pass (all existing tests green).
- 734+ project tests pass with no regressions from phantom changes.
- Verified on live vault: 347 real nodes, 93 phantom nodes, 156 edges
  to phantoms, `_invalid_links` count matches edge count exactly.

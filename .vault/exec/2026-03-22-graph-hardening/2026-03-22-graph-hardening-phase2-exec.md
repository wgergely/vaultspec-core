---
tags:
  - '#exec'
  - '#graph-hardening'
date: '2026-03-22'
related:
  - '[[2026-03-22-graph-hardening-plan]]'
---

# graph-hardening phase 2 - guards and metrics

## Changes

### `src/vaultspec_core/graph/api.py`

- Added `phantom_count: int = 0` field to `GraphMetrics` dataclass with docstring.
- Updated `metrics()` to skip phantom nodes when computing `nodes_by_type`, `total_words`, and `by_feature` counts - fixes audit api.py-002 (phantoms no longer inflate `total_nodes` or appear as "unknown" in `nodes_by_type`).
- `metrics()` now populates `phantom_count` from phantom nodes in the graph.
- `metrics()` now derives `invalid_link_count` as the count of edges whose target node has `phantom=True` - the authoritative pre-commit gate value.
- `total_nodes` in `GraphMetrics` is now `n_nodes - phantom_count` so phantom nodes do not inflate the real document count.
- Updated `get_hotspots()` to exclude phantom nodes from rankings - fixes audit api.py-003.

### `src/vaultspec_core/vaultcore/checks/references.py`

- Updated `check_references()` to skip phantom nodes when building the feature type index (`by_feature`).
- Updated `check_schema()` to skip phantom nodes in the `feat_type_index` used for fix lookups.
- Updated `check_schema()` `linked_types` computation to skip targets where `node.phantom is True`.

## Verification

- `uv run ruff check` - all checks passed
- `uv run ruff format --check` - 2 files already formatted
- `uv run python -m ty check src/vaultspec_core` - all checks passed
- `uv run pytest src/vaultspec_core/graph/tests/test_graph.py -x -q` - 53 passed
- Full regression suite - 734 passed, 6 deselected

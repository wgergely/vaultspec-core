---
tags:
  - '#exec'
  - '#test-project-removal'
date: 2026-04-12
related:
  - '[[2026-04-12-test-project-removal-plan]]'
---

# test-project-removal phase3 graph

## step reference

Plan step 3.10 - refactor `src/vaultspec_core/graph/tests/conftest.py` and
`src/vaultspec_core/graph/tests/test_graph.py`.

## files modified

- `src/vaultspec_core/graph/tests/conftest.py` - replaced `TEST_PROJECT`
  constant and `vault_root` fixture with two session-scoped fixtures:
  `graph_manifest` (returns `CorpusManifest`) and `vault_root` (returns
  `manifest.root`). No other files changed.
- `src/vaultspec_core/graph/tests/test_graph.py` - rewrote
  `test_check_schema_ignores_phantom_adr_references` to resolve the
  phantom-only plan via `graph_manifest.pathology_details["phantom_only_links"][0]["plan_doc"]`
  instead of the hardcoded stem `"2026-02-04-displaymap-integration-plan"`.

## synthetic vault parameters

```python
build_synthetic_vault(
    root,
    n_docs=120,
    seed=9,
    feature_names=["editor-demo", "displaymap-integration", "alpha-engine", "beta-pipeline"],
    named_docs={
        "editor_demo_adr": "2026-02-05-editor-demo-architecture-adr",
        "editor_demo_research": "2026-02-05-editor-demo-research",
    },
    pathologies=["cycle", "orphan", "stem_collision", "phantom_only_links"],
    graph_density=0.3,
)
```

## seed selection rationale

seed=9 was chosen after scanning seeds 0-9: it is the first seed where the
named ADR doc has a non-zero `out_links` count and the named research doc has
a non-zero `in_links` count in the built `VaultGraph`, satisfying
`test_out_links_populated` and `test_in_links_populated`.

## test accommodations

- `n_docs=120` - needed to satisfy `len(graph.nodes) > 80` (yields 131 total
  nodes including phantoms) and `m.total_nodes > 80` (129 real nodes).
- `named_docs` injection - provides the literal stems looked up by
  `graph.nodes["2026-02-05-editor-demo-architecture-adr"]` and
  `graph.nodes.get("2026-02-05-editor-demo-research")` in 8 tests across
  `TestVaultGraphBuilding` and `TestVaultGraphQueries`.
- `feature_names` - ensures `"editor-demo"` appears in `get_feature_rankings()`,
  `get_features()`, `get_feature_nodes()`, `subgraph()`, and feature-scoped
  metrics, ASCII, tree, and JSON tests.
- `pathologies=["stem_collision"]` - produces the qualified `adr/` and `plan/`
  keys for `test_colliding_stems_get_qualified_keys` and
  `test_stem_index_maps_collisions`.
- `pathologies=["phantom_only_links"]` - creates phantom nodes for the full
  `TestVaultGraphPhantom` class and the rewritten schema test.
- `pathologies=["cycle", "orphan"]` - ensures `test_builds_many_nodes_includes_phantoms`
  and orphan-related assertions hold.
- `test_check_schema_ignores_phantom_adr_references` - rewritten to accept a
  second `graph_manifest` fixture parameter and resolve plan stem via
  `pathology_details["phantom_only_links"][0]["plan_doc"].path.stem`.

## no changes to synthetic.py

`synthetic.py` was not modified. The `pathology_details["phantom_only_links"][0]["plan_doc"]`
field name confirmed to match the generator implementation at line 529-531.

## validation

- `pytest src/vaultspec_core/graph/tests/` - 66 passed
- `ruff check src/vaultspec_core/graph/tests/` - all checks passed
- `ty check src/vaultspec_core/graph/tests/` - all checks passed

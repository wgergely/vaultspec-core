---
tags:
  - '#exec'
  - '#graph-hardening'
date: '2026-03-22'
related:
  - '[[2026-03-22-graph-hardening-plan]]'
  - '[[2026-03-22-graph-hardening-phase1-exec]]'
  - '[[2026-03-22-graph-hardening-phase2-exec]]'
  - '[[2026-03-22-graph-hardening-phase3-exec]]'
  - '[[2026-03-22-graph-hardening-phase4-exec]]'
  - '[[2026-03-22-graph-hardening-phase6-exec]]'
---

# `graph-hardening` summary

All 6 phases complete. The vault graph now mirrors Obsidian's "not
created" link model with phantom nodes and a dangling-link checker.

- Modified: `src/vaultspec_core/graph/api.py`
- Modified: `src/vaultspec_core/graph/tests/test_graph.py`
- Modified: `src/vaultspec_core/vaultcore/checks/__init__.py`
- Modified: `src/vaultspec_core/vaultcore/checks/orphans.py`
- Modified: `src/vaultspec_core/vaultcore/checks/references.py`
- Modified: `src/vaultspec_core/cli/vault_cmd.py`
- Modified: `.pre-commit-config.yaml`
- Created: `src/vaultspec_core/vaultcore/checks/dangling.py`
- Created: `src/vaultspec_core/vaultcore/checks/tests/test_dangling.py`

## Description

- Phase 1: `DocNode.phantom` field, phantom node creation in
  `_build_graph()` pass 2, `_invalid_links` captures all edges to
  phantoms.
- Phase 2: `GraphMetrics.phantom_count`, phantom-aware guards on all
  query methods and checkers, `invalid_link_count` derived from edges
  to phantom targets.
- Phase 3: Tree renderer shows `(not created)` for phantom targets,
  metrics CLI shows phantom count, JSON includes `phantom` flag.
- Phase 4: `check_dangling` checker at ERROR severity with `--fix`
  support, wired into `run_all_checks()` and CLI.
- Phase 5: Pre-commit hook config prepared (commented out until vault
  is cleaned of pre-existing dangling links).
- Phase 6: 15 new tests covering phantom creation, metrics, exclusion
  guards, rendering, and dangling checker.

## Tests

- 68 graph tests pass (53 existing + 15 new).
- 749 total project tests pass with no regressions.
- Type checking (ty), linting (ruff), formatting all clean.
- Live vault correctly reports 93 phantom nodes, 157 dangling links at
  ERROR severity.

---
tags:
  - '#plan'
  - '#graph-hardening'
date: '2026-03-22'
related:
  - '[[2026-03-22-graph-hardening-adr]]'
  - '[[2026-03-22-graph-hardening-research]]'
---

# `graph-hardening` plan

Harden the vault graph to surface dangling wiki-links as first-class phantom
nodes and add a `check_dangling` checker that blocks pre-commit hooks when
unresolved links exist. Per \[[2026-03-22-graph-hardening-adr]\], a healthy
vault must have zero dangling links.

## Proposed Changes

Per \[[2026-03-22-graph-hardening-adr]\] decisions 1-6:

- Phantom `DocNode`s for unresolved wiki-link targets (mirrors Obsidian).
- New `check_dangling` checker at ERROR severity.
- `GraphMetrics.invalid_link_count` as the authoritative gate for
  pre-commit hooks.
- Phantom-aware guards on `check_schema`, `check_references`,
  `check_orphans`, `to_snapshot()`.
- Distinct rendering in tree and JSON output.

## Tasks

- `Phase 1: Phantom nodes in the graph`

  1. Add `phantom: bool = False` field to `DocNode`. Update docstring.
  1. Update `to_nx_attrs()` to include `phantom` in the returned dict.
  1. In `_build_graph()` pass 2, when `_resolve_link()` returns a target
     not in `self.nodes`, create a phantom `DocNode` (name only, no path,
     no body, `phantom=True`) and register it in `self.nodes` and
     `self._digraph`. Add a real directed edge from source to phantom.
  1. Deduplicate phantom creation - multiple sources may reference the same
     missing target. Check `self.nodes` before creating a second phantom.
  1. Update `_build_graph()` pass 3 (nx attr sync) to include phantom
     nodes.

  - **Files**: `src/vaultspec_core/graph/api.py`
  - **Verify**: Existing tests still pass (node counts will change - see
    phase 3). Phantom nodes appear in `graph.nodes` with `phantom=True`.

- `Phase 2: Guards and metrics`

  1. Update `get_orphaned()` to exclude nodes where `phantom=True`.
  1. Update `to_snapshot()` to exclude phantom nodes (no path to lint).
  1. Add `phantom_count: int = 0` field to `GraphMetrics`.
  1. Update `metrics()` to populate `phantom_count` from phantom nodes.
     Derive `invalid_link_count` as the count of edges whose target node
     has `phantom=True` - this is the authoritative pre-commit gate value.
  1. Update `check_schema` (`references.py`) to skip targets where
     `node.phantom` is `True` when computing `linked_types`.
  1. Update `check_references` (`references.py`) to skip phantom nodes
     when building the feature type index.

  - **Files**: `src/vaultspec_core/graph/api.py`,
    `src/vaultspec_core/vaultcore/checks/references.py`
  - **Verify**: `get_orphaned()` returns no phantom names. `to_snapshot()`
    has no phantom entries. `metrics().phantom_count` matches actual
    phantom node count. `invalid_link_count` equals the number of edges
    to phantoms. Existing `check_schema` and `check_references` behavior
    unchanged (phantoms were already invisible via `nodes.get()` returning
    `None` - now they are explicitly skipped).

- `Phase 3: Rendering`

  1. Update `_add_typed_nodes()` tree renderer: replace the existing
     `(broken)` label with `(not created)` styled distinctly for phantom
     targets. Phantom nodes that are link targets should render inline
     under their referencing node (current behavior), not as standalone
     tree entries.
  1. Update `to_dict()` / JSON serialization: phantom nodes include
     `phantom: true` in their node dict. Body is always empty for
     phantoms.
  1. Update `_print_metrics()` CLI output to show phantom count alongside
     invalid link count.

  - **Files**: `src/vaultspec_core/graph/api.py`,
    `src/vaultspec_core/cli/vault_cmd.py`
  - **Verify**: Tree output shows `(not created)` for phantom targets.
    JSON export includes `phantom` flag. Metrics CLI shows phantom count.

- `Phase 4: check_dangling checker`

  1. Create `src/vaultspec_core/vaultcore/checks/dangling.py` with a
     `check_dangling()` function. Signature matches existing checkers:
     accepts `root_dir`, `graph`, optional `feature`, optional `fix`.
  1. The checker iterates `graph.get_invalid_links()`. For each
     `(source, target)` pair, emit an ERROR-severity `CheckDiagnostic`
     with the source document path and the unresolved target name.
  1. With `--fix`, remove the dangling `target` entry from the source
     document's `related:` frontmatter field. Do not remove body-text
     wiki-links (too risky - body links may be intentional prose
     references).
  1. Add `check_dangling` to `checks/__init__.py`: import, `__all__`,
     and wire into `run_all_checks()` (insert after `check_links`,
     before `check_orphans` - dangling links should be reported before
     orphan analysis).
  1. Add CLI subcommand `vault check dangling` in `vault_cmd.py`.

  - **Files**: `src/vaultspec_core/vaultcore/checks/dangling.py` (new),
    `src/vaultspec_core/vaultcore/checks/__init__.py`,
    `src/vaultspec_core/cli/vault_cmd.py`
  - **Verify**: `vault check all` shows `dangling` section. ERROR
    diagnostics appear for every phantom target. `--fix` removes dead
    `related:` entries. Exit code 1 when dangling links exist.

- `Phase 5: Pre-commit hook wiring`

  1. Add a `check-dangling` hook to `.pre-commit-config.yaml` that runs
     `vault check dangling` on markdown files. Read-only (no `--fix`),
     exits non-zero when dangling links exist. The hook output must
     include the count: "N dangling links found".
  1. Verify the hook integrates with the existing read-only hook
     philosophy (no file modifications during pre-commit).

  - **Files**: `.pre-commit-config.yaml`
  - **Verify**: Committing a `.vault/` markdown file with a dangling
    wiki-link triggers the hook and blocks the commit with a clear count
    message.

- `Phase 6: Tests`

  1. Update `test_graph.py` - `test_no_nodes_lost_to_stem_collisions` to
     filter phantom nodes when comparing against `scan_vault()` file
     count.
  1. Add test: phantom nodes created for unresolved targets (check
     `node.phantom is True`, node in `graph.nodes`, edge exists in
     digraph).
  1. Add test: `get_orphaned()` excludes phantom nodes.
  1. Add test: `to_snapshot()` excludes phantom nodes.
  1. Add test: `metrics().phantom_count` matches actual phantom count.
  1. Add test: `metrics().invalid_link_count` equals edge count to
     phantom targets.
  1. Add test: `check_dangling` reports ERROR for each dangling link.
  1. Add test: `check_dangling` with `--fix` removes `related:` entry.
  1. Add test: `check_schema` does not count phantom targets as real
     references.
  1. Add test: tree rendering shows `(not created)` for phantom targets.
  1. Add test: JSON output includes `phantom: true` for phantom nodes.

  - **Files**: `src/vaultspec_core/graph/tests/test_graph.py`,
    new test file for dangling checker
  - **Verify**: Full test suite green. No regressions.

## Parallelization

- Phase 1 must complete first - all subsequent phases depend on phantom
  nodes existing in the graph.
- Phase 2 and Phase 3 are independent and can run in parallel after
  Phase 1.
- Phase 4 depends on Phase 2 (checker needs `get_invalid_links()` to
  work with the new phantom model).
- Phase 5 depends on Phase 4 (hook runs the checker).
- Phase 6 can begin after Phase 1 but should cover all phases, so runs
  last.

```
Phase 1 (phantom nodes)
  ├── Phase 2 (guards + metrics) ── Phase 4 (checker) ── Phase 5 (hook)
  └── Phase 3 (rendering)
Phase 6 (tests) - after all phases
```

## Verification

- `vault check all` on the live vault reports dangling links as ERRORs
  where previously `links: clean` was reported.
- `vault graph --metrics` shows `phantom_count` and `invalid_link_count`
  matching each other in a vault with no stem collisions.
- `vault graph` tree output shows `(not created)` labels for phantom
  targets, matching what Obsidian displays.
- Pre-commit hook blocks commits containing dangling wiki-links with a
  clear count message.
- `vault check dangling --fix` removes dead `related:` entries and
  re-running reports clean.
- All existing tests pass with phantom-aware adjustments. No test uses
  mocks, stubs, or skips.

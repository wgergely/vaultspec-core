---
tags:
  - '#plan'
  - '#cli-ambiguous-states'
date: '2026-03-27'
related:
  - '[[2026-03-27-cli-ambiguous-states-resolver-adr]]'
  - '[[2026-03-27-cli-ambiguous-states-gitignore-adr]]'
  - '[[2026-03-27-cli-ambiguous-states-research]]'
  - '[[2026-03-27-cli-ambiguous-states-prior-art-research]]'
---

# `cli-ambiguous-states` implementation plan

Implement the workspace state diagnosis/resolution engine, manifest v2.0,
gitignore managed block support, and doctor command per the two accepted
ADRs. Work is phased so each phase is independently committable, testable,
and reviewable.

## Proposed Changes

Per the resolver ADR: introduce a `core/diagnosis/` package with signal
enums and collectors, a `core/resolver.py` resolution engine, upgrade
`core/manifest.py` to v2.0 with `ManifestData` dataclass, and add a
`doctor` CLI command. Per the gitignore ADR: introduce `core/gitignore.py`
with chevron-marker managed block support. Wire both into existing
install/sync/uninstall flows.

## Tasks

- Phase 1: Foundation (signal enums, manifest v2.0, gitignore module)

  1. Create `core/diagnosis/` package with `__init__.py` and `signals.py`
     containing all 7 signal enums (`FrameworkSignal`, `ProviderDirSignal`,
     `ManifestEntrySignal`, `ContentSignal`, `BuiltinVersionSignal`,
     `ConfigSignal`, `GitignoreSignal`) plus `ResolutionAction` enum.
     Add `ProviderDiagnosis` and `WorkspaceDiagnosis` dataclasses in
     `core/diagnosis/diagnosis.py`.
  1. Upgrade `core/manifest.py` to v2.0. Add `ManifestData` dataclass
     with all v2.0 fields (`version`, `vaultspec_version`, `installed_at`,
     `serial`, `installed`, `provider_state`, `gitignore_managed`). Add
     new functions `read_manifest_data() -> ManifestData` and
     `write_manifest_data(target, data: ManifestData)`. Keep existing
     `read_manifest() -> set[str]` and `write_manifest(target, providers)`
     signatures unchanged as backward-compat wrappers. Update
     `MANIFEST_VERSION` constant to `"2.0"`. Ensure `read_manifest_data`
     handles v1.0 manifests gracefully (missing fields get zero-values).
     Update `add_providers` and `remove_provider` to use
     `read_manifest_data`/`write_manifest_data` internally while
     preserving their public signatures. Serial is incremented inside
     `write_manifest_data`.
  1. Create `core/gitignore.py` with `MARKER_BEGIN`, `MARKER_END`,
     `DEFAULT_ENTRIES`, and `ensure_gitignore_block()`. Handle: line
     ending detection/preservation via `splitlines()` + raw byte
     inspection, trailing whitespace normalization on marker comparison,
     orphaned marker cleanup (remove orphan before appending fresh block),
     atomic writes via existing `atomic_write` from `core/helpers.py`.
     Handle BOM-prefixed files (detect and preserve BOM).
  1. Write tests for phase 1 in `src/vaultspec_core/tests/cli/`:
     `test_signals.py` (signal enum membership),
     `test_manifest_v2.py` (v2.0 read/write/upgrade from v1.0, serial
     increment, backward-compat wrapper behavior),
     `test_gitignore.py` (block insertion, update, removal, orphaned
     markers, CRLF, BOM, trailing whitespace, no-file, empty-file,
     multiple trailing blank lines).

- Phase 2: Signal collectors

  1. Implement `collect_framework_presence()` in
     `core/diagnosis/collectors.py`. Checks `.vaultspec/` existence and
     `providers.json` validity. Uses deferred imports for `core.*`
     modules to prevent import cycles.
  1. Implement `collect_manifest_coherence()`. Cross-references manifest
     `installed` set against actual provider directory existence per
     `ToolConfig`. Returns `dict[Tool, ManifestEntrySignal]`.
  1. Implement `collect_provider_dir_state()`. Inspects provider
     subdirectories owned by a tool (via `ToolConfig`), classifies as
     MISSING/EMPTY/PARTIAL/COMPLETE/MIXED. For shared directories
     (`.agents/`), inspects only the subdirectories owned by the
     specific provider.
  1. Implement `collect_builtin_version_state()`. Delegates to existing
     `revert.list_modified_builtins()` and maps results to the
     `BuiltinVersionSignal` enum.
  1. Implement `collect_config_state()`. Checks root config file
     existence and `AUTO-GENERATED` marker presence (for FOREIGN
     signal). Checks `.mcp.json` for vaultspec-core entry (PARTIAL_MCP,
     USER_MCP signals).
  1. Implement `collect_gitignore_state()`. Uses marker constants from
     `core/gitignore.py` to check block presence and entry completeness.
     Detects CORRUPTED state (single orphaned marker).
  1. Implement `collect_content_integrity()`. Reuses existing
     `collect_rules()`, `collect_skills()`, etc. and transform pipelines
     to compute expected content SHA-256, compares against actual
     destination files. Gated: skipped when framework signal is
     MISSING or CORRUPTED. Uses deferred imports.
  1. Implement `diagnose()` orchestrator in
     `core/diagnosis/diagnosis.py`. Runs collectors in layered order:
     framework-presence and manifest-coherence first (no WorkspaceContext
     needed), then provider/content/config collectors (require
     WorkspaceContext, skipped if framework MISSING/CORRUPTED). Each
     collector wrapped in try/except for exception isolation. Returns
     `WorkspaceDiagnosis`. Accepts optional `scope` parameter to
     enable lazy collection: `"full"` for doctor, `"framework"` for
     install, `"sync"` for sync (skips content integrity unless
     explicitly requested).
  1. Write tests in `src/vaultspec_core/tests/cli/test_collectors.py`:
     parametrized fixtures producing each signal state per collector.
     Add `make_degraded_workspace()` factory helper to conftest.py
     that takes a clean workspace and applies named corruptions
     (`"orphaned_manifest"`, `"missing_provider_dir"`,
     `"stale_content"`, `"mixed_user_content"`, etc.).

- Phase 3: Resolver engine and doctor command (parallel tracks)

  1. Create `core/resolver.py` with `ResolutionStep`, `ResolutionPlan`
     dataclasses and `resolve()` function. Implement the full resolution
     rule matrix from the ADR (18 rules). `resolve()` accepts
     `dry_run` parameter. Supports `provider="all"` by iterating all
     providers internally. Provider-independent steps ordered before
     provider-specific steps. Include version-mismatch warning when
     running vaultspec version is older than manifest's
     `vaultspec_version`.
  1. Add `doctor` command to `cli/root.py`. Calls `diagnose(scope="full")`
     and formats human-readable table output. Support `--json` flag
     for structured output. Exit codes: 0 (ok/info), 1 (warnings),
     2 (errors/conflicts). Does not depend on resolver - uses diagnosis
     directly.
  1. Write tests in `src/vaultspec_core/tests/cli/`:
     `test_resolver.py` (parametrized by signal/action/force, covering
     all 18 rules, plus no-op verification test asserting filesystem
     unchanged when conflicts are present),
     `test_doctor.py` (human-readable output format, JSON output,
     exit codes for clean and degraded states).

- Phase 4: CLI integration and command wiring

  1. Wire gitignore block into commands: `install_run()` calls
     `ensure_gitignore_block()` after sync, sets `gitignore_managed`
     in manifest. Handle `--upgrade --force` re-opt-in (resets
     `gitignore_managed` to true). `uninstall_run()` calls
     `ensure_gitignore_block(state="absent")` on `--force`.
     `sync_provider()` checks `gitignore_managed` flag: if true,
     update block; if block was removed by user (markers not found
     but flag was true), set flag to false and emit warning.
  1. Update `install_run()` and `sync_provider()` to populate v2.0
     manifest fields: `vaultspec_version` (from package metadata),
     `installed_at` (ISO timestamp on install), `serial` (auto-
     incremented by `write_manifest_data`), `provider_state`
     timestamps (`installed_at`, `last_synced` per provider).
  1. Wire resolver as pre-flight into CLI handlers in `cli/root.py`.
     Insertion point: after `_t.set_context()` but before
     `_ensure_tool_configs()` for framework/manifest collectors.
     After `_ensure_tool_configs()` for provider/content collectors
     (if needed based on scope). Wire `dry_run` parameter through.
     Existing inline guards in `commands.py` preserved as
     defense-in-depth.
  1. Write integration tests in
     `src/vaultspec_core/tests/cli/test_ambiguous_states.py`:
     the 12 key scenarios from the research, using the
     `make_degraded_workspace()` factory. Split into fixture setup
     (the factory) and scenario execution (parametrized test
     functions). Scenarios: vanilla install, partial install,
     corrupted manifest, orphaned directories, stale content, mixed
     content, pre-existing provider config, empty directories, old
     version install, missing builtins, no gitignore, partial
     gitignore.

## Parallelization

- Phase 1 steps 1-3 are fully independent (signals, manifest,
  gitignore) - three parallel sub-agents. Step 4 (tests) depends on 1-3.
- Phase 2 collectors 1-7 are independent. Step 8 (orchestrator) depends
  on all collectors. Step 9 (tests) depends on step 8.
- Phase 3 steps 1 and 2 are independent (resolver and doctor). Step 3
  (tests) depends on both.
- Phase 4 steps are sequential.

## Verification

- All existing tests must continue to pass. The backward-compat shim
  strategy (`read_manifest`/`write_manifest` signatures preserved)
  ensures zero regressions from manifest v2.0.
- New unit tests for every signal enum, collector, resolver rule, and
  gitignore edge case.
- Integration tests for the 12 key ambiguous state scenarios.
- `vaultspec-core doctor` must produce correct output for clean and
  degraded states.
- No-op verification test: filesystem unchanged when resolver returns
  conflicts (Stow's accumulation pattern).
- Pre-commit hooks and lints must pass on all new code.

---
tags:
  - '#plan'
  - '#mcp-registry'
date: '2026-04-11'
related:
  - '[[2026-04-11-mcp-registry-adr]]'
  - '[[2026-04-11-mcp-registry-research]]'
---

# `mcp-registry` `phase-1` plan

Implement the MCP server registry: built-in MCP definitions stored in
`.vaultspec/rules/mcps/`, a new `core/mcps.py` module with collect/list/
add/remove/sync functions, CLI subcommands (`spec mcps`), lifecycle
integration with install/sync/uninstall, and doctor diagnostics for
registry drift detection. Replaces the hardcoded `_scaffold_mcp_json()`
with a data-driven pipeline.

## Proposed Changes

Per the accepted ADR, the implementation uses a standalone MCP sync
pipeline (Option A) that operates on JSON definition files rather than
adapting the Markdown-based `sync_to_all_tools()` abstraction. The
`_scaffold_mcp_json()` function is superseded by `mcp_sync()`.

## Tasks

- Phase 1: Foundation (enums, types, built-in definition)

  - [ ] Step 1.1: Add `MCPS = "mcps"` to `Resource` enum in `core/enums.py`
  - [ ] Step 1.2: Add `mcps_src_dir: Path` field to `WorkspaceContext` in `core/types.py`; update ALL construction sites: `init_paths()` (types.py:334), `uninstall_run()` bootstrap (commands.py:787), `install_upgrade()` bootstrap (commands.py:538), `_target.py` fallback context (cli/\_target.py:166), and any test fixtures that construct `WorkspaceContext` directly (tests/cli/conftest.py, tests/cli/test_sync_manifest.py). Consider giving the field a default value to ease construction.
  - [ ] Step 1.3: Create the built-in definition file `.vaultspec/rules/mcps/vaultspec-core.builtin.json` containing the server config currently hardcoded in `_scaffold_mcp_json()`

- Phase 2: Core module (`core/mcps.py`)

  - [ ] Step 2.1: Implement `collect_mcp_servers(warnings)` - reads `.json` files from `mcps_src_dir`, parses each, returns `dict[str, tuple[Path, dict]]` mapping server name (derived from filename) to (source path, parsed config); filename stem extraction must strip `.builtin.json` as a unit first, then fall back to `.json` (handles `foo.bar.builtin.json` -> `foo.bar`); must return empty dict gracefully when `mcps_src_dir` does not exist (fresh workspace before seeding)
  - [ ] Step 2.2: Implement `mcp_list()` - returns `list[dict[str, str]]` with `name` and `source` ("Built-in" or "Custom") fields, mirroring `rules_list()` pattern
  - [ ] Step 2.3: Implement `mcp_add(name, config, force)` - writes a new `.json` file to `mcps_src_dir`; validates JSON structure; raises `ResourceExistsError` if exists and not `force`
  - [ ] Step 2.4: Implement `mcp_remove(name)` - finds and deletes the definition file; raises `ResourceNotFoundError` if not found
  - [ ] Step 2.5: Implement `mcp_sync(dry_run, force)` - the core merge pipeline: collect definitions, read/initialize `.mcp.json`, merge entries (add missing, skip matching, warn on diff without force / overwrite with force), atomic write, return `SyncResult` (imported from `core/types.py`); must also call `ensure_dir(mcps_src_dir)` to handle missing directory gracefully

- Phase 3: Lifecycle integration (`core/commands.py`)

  - [ ] Step 3.1: Replace `_scaffold_mcp_json(target)` call in `init_run()` (line ~428) with `mcp_sync()` call, gated by `"mcp" not in skip`
  - [ ] Step 3.2: Add `mcp_sync` to `_run_all_syncs()` list in `sync_provider()` alongside rules/skills/agents/system/config; the `--skip mcp` gating is handled by the caller (sync_provider checks skip before calling \_run_all_syncs for the "all" path, and mcp_sync runs unconditionally within \_run_all_syncs since it targets a provider-agnostic file)
  - [ ] Step 3.3: Remove the standalone `_scaffold_mcp_json()` repair call in `sync_provider()` (line ~1270) - now handled by `_run_all_syncs()`
  - [ ] Step 3.4: Replace `_scaffold_mcp_json()` calls in `install_upgrade()`: (a) the dry-run manifest path at line ~584 should call `mcp_sync(dry_run=True)` or equivalent, (b) the upgrade repair call at line ~623 is removed (now handled via `sync_provider()` which calls `_run_all_syncs()`), (c) add `"mcps": len(collect_mcp_servers())` to `source_counts`
  - [ ] Step 3.5: Replace hardcoded `vaultspec-core` key removal in `uninstall_run()` (line ~901) with registry-aware cleanup: collect managed server names, remove each from `.mcp.json`, delete file if empty; this applies only to full uninstall (`effective_provider == "all"`); per-provider uninstall leaves MCP untouched
  - [ ] Step 3.6: Search for ALL remaining `_scaffold_mcp_json` references; once all callsites are migrated, remove the function entirely

- Phase 4: Public API and CLI

  - [ ] Step 4.1: Add re-exports to `core/__init__.py`: `collect_mcp_servers`, `mcp_list`, `mcp_add`, `mcp_remove`, `mcp_sync`
  - [ ] Step 4.2: Add `mcps_app` Typer sub-group to `cli/spec_cmd.py` with commands: `list`, `add`, `remove`, `sync` - mirroring the `rules_app` pattern (including `--json`, `--force`, `--dry-run`, `--target` options)

- Phase 5: Doctor diagnostics

  - [ ] Step 5.1: Add `REGISTRY_DRIFT` value to `ConfigSignal` enum in `diagnosis/signals.py`; update the signal display dict in `cli/root.py` (line ~867-875) to include a human-readable label; update the if-elif chain in `diagnosis/resolver.py` (line ~539-552) to handle the new signal
  - [ ] Step 5.2: Extend `collect_mcp_config_state()` in `diagnosis/collectors.py` to compare deployed `.mcp.json` entries against registry definitions; return `REGISTRY_DRIFT` when managed entries are missing or have stale configuration

- Phase 6: Tests

  - [ ] Step 6.1: Unit tests for `collect_mcp_servers()` - empty dir, missing dir, single builtin, custom, mixed, parse errors, multi-dot filename stems (`foo.bar.builtin.json`)
  - [ ] Step 6.2: Unit tests for `mcp_list()`, `mcp_add()`, `mcp_remove()` - CRUD operations, error cases
  - [ ] Step 6.3: Unit tests for `mcp_sync()` - idempotent merge, non-destructive preserve, warn on diff without force, force overwrite, dry-run, empty state, missing `.mcp.json`
  - [ ] Step 6.4: Integration tests for CLI subcommands via Typer test runner
  - [ ] Step 6.5: Integration tests for lifecycle: install seeds MCPs, sync repairs drift, uninstall cleans managed entries
  - [ ] Step 6.6: Test for doctor diagnostics: REGISTRY_DRIFT detection

- Phase 7: Finalization

  - [ ] Step 7.1: Run `uv run ruff check` and `uv run ty check` on all modified files; fix any issues
  - [ ] Step 7.2: Run full test suite `uv run pytest` and verify all tests pass
  - [ ] Step 7.3: Commit changes and open/update draft PR

## Parallelization

- Phase 1 steps are sequential (each depends on prior)
- Phase 2 steps 2.1-2.4 are independent; 2.5 depends on 2.1
- Phase 3 steps are mostly independent but should be applied sequentially to avoid merge conflicts within `commands.py`
- Phase 4 depends on Phase 2
- Phase 5 is independent of Phases 3-4
- Phase 6 depends on all prior phases
- Phase 7 depends on all prior phases

## Verification

- All existing tests continue to pass (no regressions)
- New unit tests cover: collection from empty/populated dirs, builtin vs custom classification, filename stem extraction for both suffixes, JSON parse error handling, idempotent sync, non-destructive merge preserving user entries, force overwrite, dry-run mode
- Integration tests verify the full lifecycle: `install` seeds the builtin definition and merges to `.mcp.json`; `sync` repairs missing/drifted entries; `uninstall` removes managed entries cleanly
- CLI subcommands produce correct output for `--json` and table modes
- `ruff check` and `ty check` report zero errors on modified files
- Pre-commit hooks pass on all staged files
- The existing `test_mcp_config.py` tests continue to pass (`.mcp.json` at repo root still valid)

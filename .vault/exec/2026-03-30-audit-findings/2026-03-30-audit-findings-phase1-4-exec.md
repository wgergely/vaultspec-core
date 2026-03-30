---
tags:
  - '#exec'
  - '#audit-findings'
date: '2026-03-30'
related:
  - '[[2026-03-30-audit-findings-plan]]'
  - '[[2026-03-27-cli-ambiguous-states-audit]]'
---

# `audit-findings` phase 1-4 step

Implemented all remaining open findings from phases 1-4 of the
audit findings plan. Many phase 1-3 items were already fixed by
prior work (PR #18, commits 68b882a, 6e42663). This step addresses
the ~17 items that were still open.

- Modified: `src/vaultspec_core/core/helpers.py`
- Modified: `src/vaultspec_core/hooks/engine.py`
- Modified: `src/vaultspec_core/core/rules.py`
- Modified: `src/vaultspec_core/core/skills.py`
- Modified: `src/vaultspec_core/core/system.py`
- Modified: `src/vaultspec_core/core/agents.py`
- Modified: `src/vaultspec_core/protocol/providers/base.py`
- Modified: `src/vaultspec_core/core/commands.py`
- Modified: `src/vaultspec_core/core/gitignore.py`
- Modified: `src/vaultspec_core/core/manifest.py`
- Modified: `src/vaultspec_core/core/config_gen.py`
- Modified: `src/vaultspec_core/builtins/__init__.py`
- Modified: `src/vaultspec_core/core/revert.py`
- Modified: `src/vaultspec_core/core/sync.py`
- Modified: `src/vaultspec_core/cli/spec_cmd.py`
- Modified: `src/vaultspec_core/cli/vault_cmd.py`
- Modified: `src/vaultspec_core/core/diagnosis/collectors.py`
- Modified: `src/vaultspec_core/tests/cli/test_gitignore.py`

## Description

### Phase 1: Data safety

- R3-S4: Added symlink guard to `ensure_dir` - refuses to create
  directories inside symlink targets.
- R2-D1/R3-S1/R2-D2/R3-S3 (already fixed): `_rmtree_robust` with
  symlink check and Windows onerror handler was already in place.
- R2-D3/R3-SEC1/R3-M2 (already fixed): surgical `.mcp.json`
  removal was already implemented.
- R2-B1/R3-F1 (already fixed): `gitignore_managed` flag fix was
  already in place.
- R4-T1/R3-S2 (already fixed): uninstall ordering (`.vaultspec/`
  last) was already implemented.

### Phase 2: Error visibility

- R5-S2: Elevated `fire_hooks()` failure logging from DEBUG to
  WARNING.
- R5-S6/R5-D1: Added `warnings` parameter to `collect_md_resources`,
  `collect_skills`, `collect_system_parts` and their wrappers
  (`collect_rules`, `collect_agents`). Sync functions now propagate
  parse warnings into `SyncResult.warnings`.
- R5-D2: Added `warnings` parameter to `resolve_includes`. Include
  failures now append to warnings list in addition to embedding
  HTML error comments.
- R5-S1/R6-DF1 (already fixed): `SyncResult.errors` display and
  exit code 1 were already implemented.
- R6-DF2 (already fixed): `_merge()` warnings propagation was
  already in place.
- R5-S3/R4-EX4 (already fixed): preflight logging at WARNING was
  already done.
- R5-S4/R4-EX5 (already fixed): `config_gen.py` and `sync.py`
  silent catches were already fixed.
- R5-S5 (already fixed): `vault_tools.py` body read logging was
  already added.

### Phase 3: Logic and return value fixes

- R4-T2: Wrapped `sync_provider` in `install_run` with try/except;
  errors collected in return dict.
- R5-L3: Removed try/except OSError from `ensure_gitignore_block` -
  OSError now propagates to callers. Updated test expectation.
- R5-L2: Added `strict` parameter to `read_manifest_data`. When
  `strict=True`, corrupt JSON raises `VaultSpecError`. Default
  `False` preserves backward compatibility.
- R5-L5: Added `logger.warning` to `_is_cli_managed` on read
  failure instead of silent False return.
- R3-P3: Verified CORRUPTED+sync preflight already executes repair
  correctly.
- R2-B2/R3-F2 (already fixed): flag precedence was correct.
- R4-T3 (already fixed): sync pass isolation was already done.

### Phase 4: Exception boundaries and hardening

- R4-FS3: `atomic_write` now uses PID-based unique temp suffix.
- R4-FS4: `atomic_write` Windows fallback uses `finally` for
  tmp cleanup.
- R4-T5: `_ensure_tool_configs` tempdir cleaned up in `finally`.
- R4-T4: `seed_builtins` and `snapshot_builtins` collect errors
  per-file and continue.
- R3-SEC5: `_write` in gitignore.py uses atomic tmp+rename pattern.
- R6-SI2: `_sync_supporting_files` handles `FileNotFoundError`.
- R6-CG2: `_sync_managed_md` catches `TagError` from
  `upsert_block`.
- R6-SI3: `providers_sharing_dir` validates directory exists on
  disk.
- R4-EX1: `spec_cmd.py` `_handle_error` now handles `OSError`;
  resource commands catch `(VaultSpecError, OSError)`.
- R4-EX2: `vault_cmd.py` commands have `OSError` handling.
- R4-EX7: Verified no duplicate `_handle_error`.
- R5-L6: Collector functions log at WARNING for `OSError`.

## Tests

All 680 existing tests pass. Ruff linting clean. One test updated:
`TestReadOnlyGitignore` now expects `OSError` instead of `False`
return from `ensure_gitignore_block`.

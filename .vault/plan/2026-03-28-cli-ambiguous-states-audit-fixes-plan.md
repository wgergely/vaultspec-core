---
tags:
  - '#plan'
  - '#cli-ambiguous-states'
date: '2026-03-28'
related:
  - '[[2026-03-27-cli-ambiguous-states-audit]]'
  - '[[2026-03-27-cli-ambiguous-states-resolver-adr]]'
  - '[[2026-03-27-cli-ambiguous-states-plan]]'
  - '[[2026-03-27-cli-ambiguous-states-prior-art-research]]'
---

# `cli-ambiguous-states` audit fix plan

Triage of 91 open findings from 6 audit rounds into actionable fixes.
Deduplicated (many findings are the same root cause reported across
rounds). Scoped to issues fixable within this PR branch. Excludes
by-design items, deferred items, and pre-existing issues outside this
feature's scope.

## Proposed Changes

Findings are deduplicated into 12 concrete fixes across 3 phases.
Each fix addresses one or more audit IDs.

## Tasks

- Phase A: Data safety (prevents data loss)

  1. Add `_rmtree_robust()` helper to `core/helpers.py`. Checks
     `is_symlink()` before rmtree (unlinks symlink instead of
     following), passes `onerror` handler that clears NTFS read-only
     attribute on Windows. Replace all 4 production `shutil.rmtree`
     calls in `commands.py`, `sync.py`, `resources.py`.
     Fixes: R2-D1, R2-D2, R3-S1, R3-S3, R2-W1, R2-W2.
  1. Surgical `.mcp.json` removal in `uninstall_run`. Remove only the
     `vaultspec-core` key from `mcpServers`, preserve user entries.
     Delete file only if no servers remain. Also fix
     `_scaffold_mcp_json` to merge into existing `.mcp.json`.
     Fixes: R2-D3, R3-M1, R3-SEC1, R3-M2, R3-SEC6.
  1. Fix `gitignore_managed` bug. In `install_run`, set
     `gitignore_managed = True` when block already exists (not just
     when `ensure_gitignore_block` returns True). Check for marker
     presence in file.
     Fixes: R2-B1, R3-F1.
  1. Reorder uninstall to delete `.vaultspec/` LAST. Provider dirs
     and files first, manifest update after each provider, framework
     dir last. Wrap each deletion in try/except to collect errors
     and continue.
     Fixes: R4-T1, R3-S2.

- Phase B: Error visibility (errors reach the user)

  1. Display `SyncResult.errors` messages in `cmd_sync`. Iterate
     `r.errors` alongside `r.warnings` in the CLI rendering. Set
     exit code 1 when any errors present.
     Fixes: R5-S1, R5-L1, R6-DF1.
  1. Fix `agents.py` `_merge()` to propagate warnings.
     Add `total.warnings.extend(result.warnings)`.
     Fixes: R6-DF2.
  1. Add `except OSError` clause to `cmd_install`, `cmd_uninstall`,
     `cmd_sync` in `root.py`. Converts filesystem errors to clean
     CLI messages instead of raw tracebacks. Also add `.vaultspec`
     is-file guard.
     Fixes: R2-E1, R2-E2, R3-M3, R3-M4.
  1. Elevate `_run_preflight` logging from DEBUG to WARNING.
     Fixes: R5-S3, R5-L4, R4-EX4.
  1. Add logging to silent catches: `config_gen.py:100` (add
     `logger.warning`), `sync.py:57` (narrow to `OSError`, add
     `logger.debug`), `mcp_server/vault_tools.py:172` (add
     `logger.warning`).
     Fixes: R5-S4, R5-S5, R4-EX3, R4-EX5.

- Phase C: Flag + logic fixes

  1. Fix `install --upgrade --dry-run` flag precedence. Check
     `upgrade` before `dry_run` in `install_run`. When both set,
     show upgrade-specific preview.
     Fixes: R2-B2, R3-F2.
  1. Guard `install --skip core` when `.vaultspec/` absent. Emit
     clear error instead of crashing during sync phase.
     Fixes: R2-B3, R3-F3.
  1. Wrap sync passes in `sync_provider` with individual try/except.
     Each pass catches exceptions independently so one failure does
     not prevent the others. Accumulate errors.
     Fixes: R4-T3.

## Not in scope (deferred or by-design)

- R1-M2, R3-P1: MIXED signal unreachable - deferred to future
- R1-M6: DIVERGED signal unreachable - SHA-256 deferred by design
- R3-P4: scope="sync" skips content integrity - by design
- R3-SEC2: sync overwrites user edits - by design (source authoritative)
- R3-SEC4: no interactive confirmation - by design for CLI
- R4-FS1/FS2: non-atomic writes across codebase - systemic, separate PR
- R4-C1/C2: file locking - systemic, separate PR
- R4-EX6: exception hierarchy unification - separate PR
- R6-SI1: path traversal via config - needs separate ADR (security)
- R6-CG1: circular include guard - separate PR
- R6-CG2: TagError crash in MD config sync - separate PR
- R3-SEC3: sync prune deletes user .md files - needs content-ownership heuristic, separate ADR
- R1-W4, R3-F4, R3-P2, R5-D3/D4/D5, R6-SI4/SI5: low severity

## Verification

- All existing 598+ tests must pass
- New tests for rmtree_robust (symlink, read-only, error collection)
- New tests for surgical .mcp.json removal
- New tests for SyncResult.errors display and exit code
- Pre-commit hooks must pass

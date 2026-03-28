---
tags:
  - '#audit'
  - '#cli-ambiguous-states'
date: '2026-03-27'
related:
  - '[[2026-03-27-cli-ambiguous-states-resolver-adr]]'
  - '[[2026-03-27-cli-ambiguous-states-gitignore-adr]]'
  - '[[2026-03-27-cli-ambiguous-states-plan]]'
---

# `cli-ambiguous-states` rolling audit

Rolling audit tracking all findings from code review and QA swarms.
Updated after each audit round. Findings are cumulative - resolved
items are marked with the commit that fixed them.

## Round 1: Phase 1 code review (post-implementation)

Conducted after initial phase 1 implementation (signals, manifest v2.0,
gitignore module).

| ID    | Severity | Finding                                                                     | Status                                               |
| ----- | -------- | --------------------------------------------------------------------------- | ---------------------------------------------------- |
| R1-I1 | HIGH     | `_find_markers` does not guard against inverted markers (begin > end)       | FIXED `6ae7e8f`                                      |
| R1-I2 | HIGH     | `_find_markers` silently takes last occurrence of duplicate markers         | FIXED `6ae7e8f`                                      |
| R1-I3 | HIGH     | `_add_block` idempotency check compares wrong original (string vs lines)    | FIXED `6ae7e8f`                                      |
| R1-I4 | HIGH     | `Tool` import in `diagnosis.py` is TYPE_CHECKING-only but needed at runtime | FIXED `6ae7e8f`                                      |
| R1-W1 | MEDIUM   | `write_manifest_data` mutates input argument                                | FIXED `6ae7e8f`                                      |
| R1-W2 | MEDIUM   | `read_manifest_data` does not validate serial is non-numeric                | FIXED `105ea84`                                      |
| R1-W4 | LOW      | `ensure_gitignore_block` state parameter is bare string not enum            | OPEN - by design, Literal type annotation sufficient |

## Round 1: Phase 2-3 code review

Conducted after collectors, resolver, and doctor command implementation.

| ID    | Severity | Finding                                                                               | Status                                |
| ----- | -------- | ------------------------------------------------------------------------------------- | ------------------------------------- |
| R1-H1 | HIGH     | `collect_mcp_config_state` crashes on non-dict JSON or null mcpServers                | FIXED `bb560b1`                       |
| R1-H2 | HIGH     | `collect_mcp_config_state` never called by `diagnose()`                               | FIXED `bb560b1`                       |
| R1-H3 | HIGH     | CORRUPTED framework blocks ALL provider diagnosis                                     | FIXED `bb560b1`                       |
| R1-M1 | MEDIUM   | `_TOOL_DIR` hardcoded mapping can fall out of sync with Tool enum                     | FIXED `105ea84`                       |
| R1-M2 | MEDIUM   | `ProviderDirSignal.MIXED` unreachable in collector                                    | OPEN - deferred to future, documented |
| R1-M5 | MEDIUM   | `collect_gitignore_state` reimplements marker finding (diverges from `_find_markers`) | FIXED `105ea84`                       |
| R1-M6 | MEDIUM   | `ContentSignal.DIVERGED` unreachable (SHA-256 deferred)                               | OPEN - by design, documented          |
| R1-M7 | MEDIUM   | `scope` parameter accepts any string silently                                         | FIXED `105ea84`                       |

## Round 1: Critical + high audit (post-all-phases)

Conducted after all 4 phases complete with full swarm.

| ID     | Severity | Finding                                                                     | Status          |
| ------ | -------- | --------------------------------------------------------------------------- | --------------- |
| R1-C1  | CRITICAL | Non-atomic manifest write (crash leaves corrupted file)                     | FIXED `bb560b1` |
| R1-C2  | CRITICAL | `resolve()` silently produces empty plans for action="upgrade" and "doctor" | FIXED `bb560b1` |
| R1-H4  | HIGH     | `remove_provider` does not clean up `provider_state` entries                | FIXED `bb560b1` |
| R1-H5  | HIGH     | Gitignore opt-out detection in sync is dead code / unreachable              | FIXED `bb560b1` |
| R1-H6  | HIGH     | Missing `.gitignore` causes silent skip but manifest claims managed=True    | FIXED `bb560b1` |
| R1-H7  | HIGH     | Upgrade path does not populate `installed_at` or per-provider timestamps    | FIXED `bb560b1` |
| R1-H8  | HIGH     | ORPHANED+install and UNTRACKED+uninstall unhandled in resolver              | FIXED `bb560b1` |
| R1-H9  | HIGH     | Doctor exit code ignores ConfigSignal and ProviderDirSignal.MISSING         | FIXED `bb560b1` |
| R1-H10 | HIGH     | No `_resolve_*` function has exhaustive match for new enum values           | FIXED `bb560b1` |

## Round 1: Medium fixes

| ID        | Severity | Finding                                                              | Status          |
| --------- | -------- | -------------------------------------------------------------------- | --------------- |
| R1-M8     | MEDIUM   | Read-only `.gitignore` causes unhandled PermissionError              | FIXED `105ea84` |
| R1-M10    | MEDIUM   | `sync_provider` updates `provider_state` for non-installed providers | FIXED `105ea84` |
| R1-M-doc  | MEDIUM   | `diagnose()` can throw unhandled in `cmd_doctor`                     | FIXED `105ea84` |
| R1-M3-res | MEDIUM   | `_resolve_version_warning` has no logging on failure                 | FIXED `105ea84` |

## Round 2: Full command QA swarm (5 agents)

Conducted after pre-flight wiring. Each agent stress-tested one domain
with exhaustive flag/state combinations.

### Bugs (incorrect behavior)

| ID    | Severity | Finding                                                                                                                                                         | Status |
| ----- | -------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| R2-B1 | HIGH     | `gitignore_managed` set to False on idempotent re-install with `--force` - `ensure_gitignore_block` returns False when block already matches, clearing the flag | OPEN   |
| R2-B2 | HIGH     | `install --upgrade --dry-run` silently ignores `--upgrade` - dry_run branch checked before upgrade branch, upgrade never evaluated                              | OPEN   |
| R2-B3 | MEDIUM   | `install --skip core <provider>` partially scaffolds provider dirs then fails during sync (no `.vaultspec/` source to sync from)                                | OPEN   |
| R2-B4 | MEDIUM   | Preflight resolution steps displayed as "will repair" but never executed - misleading for corrupted manifest + sync                                             | OPEN   |

### Data loss risks

| ID    | Severity | Finding                                                                                                                      | Status |
| ----- | -------- | ---------------------------------------------------------------------------------------------------------------------------- | ------ |
| R2-D1 | CRITICAL | `shutil.rmtree` on symlinked provider dirs follows symlink, destroys target directory contents outside workspace             | OPEN   |
| R2-D2 | HIGH     | `shutil.rmtree` fails on Windows locked/read-only files with no `onerror` handler, leaves partial uninstall with no rollback | OPEN   |
| R2-D3 | HIGH     | `.mcp.json` fully deleted on `uninstall all` - user MCP server entries for other tools are lost                              | OPEN   |

### Missing error handling

| ID    | Severity | Finding                                                                                               | Status |
| ----- | -------- | ----------------------------------------------------------------------------------------------------- | ------ |
| R2-E1 | MEDIUM   | `PermissionError` not caught in `install_run` for read-only target directories - raw Python traceback | OPEN   |
| R2-E2 | MEDIUM   | `.vaultspec` existing as a file (not directory) causes raw `FileExistsError`/`NotADirectoryError`     | OPEN   |
| R2-E3 | LOW      | `doctor --target /nonexistent` shows "framework missing" instead of "directory does not exist"        | OPEN   |

### Untested but handled scenarios

| ID     | Domain    | Scenario                                                                | Status   |
| ------ | --------- | ----------------------------------------------------------------------- | -------- |
| R2-U1  | Install   | `install core` (framework only)                                         | UNTESTED |
| R2-U2  | Install   | `install claude` (single provider)                                      | UNTESTED |
| R2-U3  | Install   | `install --upgrade --force` gitignore re-opt-in                         | UNTESTED |
| R2-U4  | Install   | `install --skip core`, `--skip claude --skip gemini`                    | UNTESTED |
| R2-U5  | Install   | `install nonexistent_provider` at CLI level                             | UNTESTED |
| R2-U6  | Install   | `.mcp.json` merge behavior (pre-existing user entries)                  | UNTESTED |
| R2-U7  | Sync      | `sync claude` (single provider) at CLI level                            | UNTESTED |
| R2-U8  | Sync      | `sync --dry-run --force` combination                                    | UNTESTED |
| R2-U9  | Sync      | `sync --skip` combinations at CLI level                                 | UNTESTED |
| R2-U10 | Sync      | `sync antigravity` when only claude installed                           | UNTESTED |
| R2-U11 | Sync      | Gitignore opt-out detection (block removed by user)                     | UNTESTED |
| R2-U12 | Sync      | Shared `.agents/` sync interleaving between providers                   | UNTESTED |
| R2-U13 | Uninstall | `uninstall claude --force` (single provider) at CLI level               | UNTESTED |
| R2-U14 | Uninstall | `uninstall --skip` combinations                                         | UNTESTED |
| R2-U15 | Uninstall | `uninstall claude` when claude not installed                            | UNTESTED |
| R2-U16 | Uninstall | Shared dir protection lifecycle (sequential uninstalls)                 | UNTESTED |
| R2-U17 | Doctor    | `doctor --json` schema completeness (mcp field, provider sub-structure) | UNTESTED |
| R2-U18 | Doctor    | `doctor` on v1.0 manifest workspace                                     | UNTESTED |
| R2-U19 | Cross-cmd | `install claude` then `install gemini` (additive install)               | UNTESTED |
| R2-U20 | Cross-cmd | `uninstall claude` then `install claude` (reinstall after selective)    | UNTESTED |
| R2-U21 | Cross-cmd | `install` -> delete `.claude/` -> `sync --force` (self-heal)            | UNTESTED |
| R2-U22 | Cross-cmd | `install` (no .gitignore) -> create .gitignore -> `sync`                | UNTESTED |

### Windows-specific findings

| ID    | Severity | Finding                                                                      | Status                                      |
| ----- | -------- | ---------------------------------------------------------------------------- | ------------------------------------------- |
| R2-W1 | HIGH     | `shutil.rmtree` fails on Windows locked files (IDE, antivirus)               | OPEN (same as R2-D2)                        |
| R2-W2 | MEDIUM   | `shutil.rmtree` fails on NTFS read-only attribute without `onerror`          | OPEN (same as R2-D2)                        |
| R2-W3 | MEDIUM   | `atomic_write` uses text-mode `write_text`, silently converts `\n` to `\r\n` | OPEN - low impact, `json.loads` is agnostic |
| R2-W4 | MEDIUM   | No file locking on concurrent manifest read-modify-write                     | OPEN - advisory serial counter only         |

### Platform-safe findings (no action needed)

- Path handling: all `_rel()` calls normalize backslashes. Collectors
  use `Path` objects. No string path comparison issues.
- Unicode/spaces/parens in paths: all handled via `pathlib.Path`.
- Long paths: typical paths well under 260 chars. Python 3.6+ handles
  with registry setting.
- CRLF in `.gitignore`: detection and preservation works correctly.
  Binary-mode write prevents doubling.
- `AUTO-GENERATED` marker detection: substring check, line-ending agnostic.

## Round 3: Deep-dive swarm (5 agents, targeted domains)

Conducted after pre-flight wiring. Each agent deep-dived into a specific
high-yield domain with concrete fix proposals.

### Symlinks + rmtree data loss (agent: r3-symlink-rmtree)

| ID    | Severity | Finding                                                                                                                                                                                                               | Status |
| ----- | -------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| R3-S1 | CRITICAL | Zero `is_symlink()` checks in entire codebase. `shutil.rmtree` on symlinked provider dirs follows symlink, destroys target directory contents. 8 affected call sites across `commands.py`, `sync.py`, `resources.py`. | OPEN   |
| R3-S2 | CRITICAL | No rollback on partial uninstall failure. If rmtree raises mid-way, some dirs already deleted, manifest inconsistent.                                                                                                 | OPEN   |
| R3-S3 | HIGH     | No `onerror`/`onexc` handler for Windows locked/read-only files. `shutil.rmtree` fails on NTFS read-only attribute.                                                                                                   | OPEN   |
| R3-S4 | MEDIUM   | `ensure_dir` creates directories inside symlink targets without warning.                                                                                                                                              | OPEN   |

Proposed fix: add `_rmtree_robust()` helper to `helpers.py` with symlink guard + Windows onerror handler. Replace all 4 production `shutil.rmtree` calls.

### Flag precedence + state bugs (agent: r3-flag-bugs)

| ID    | Severity | Finding                                                                                                                                                                                                                         | Status |
| ----- | -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| R3-F1 | HIGH     | `gitignore_managed` cleared on idempotent re-install with `--force`. `ensure_gitignore_block` returns False when block matches, `mdata.gitignore_managed = gi_written` sets False. Fix: check block presence, not return value. | OPEN   |
| R3-F2 | HIGH     | `install --upgrade --dry-run` silently ignores `--upgrade`. `if dry_run:` checked before `if upgrade:`, upgrade branch never reached.                                                                                           | OPEN   |
| R3-F3 | MEDIUM   | `install --skip core <provider>` scaffolds provider dirs then fails during sync (no `.vaultspec/` source). No guard.                                                                                                            | OPEN   |
| R3-F4 | LOW      | Preflight resolution steps displayed as "will repair" but never executed. By design (phased), but messaging is misleading.                                                                                                      | OPEN   |

### MCP + .vaultspec-as-file (agent: r3-mcp-vaultspec-file)

| ID    | Severity | Finding                                                                                                                                              | Status |
| ----- | -------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| R3-M1 | HIGH     | `.mcp.json` fully deleted on `uninstall all`. User MCP server entries for other tools destroyed. Fix: surgical removal of `vaultspec-core` key only. | OPEN   |
| R3-M2 | MEDIUM   | `_scaffold_mcp_json` skips if `.mcp.json` exists, never merges vaultspec-core entry into existing config.                                            | OPEN   |
| R3-M3 | MEDIUM   | `.vaultspec` as a file causes raw `NotADirectoryError` (with --force) or misleading "already installed" (without). Fix: add `is_dir()` guard.        | OPEN   |
| R3-M4 | MEDIUM   | `PermissionError` not caught in `cmd_install`/`cmd_uninstall`/`cmd_sync`. Fix: add `except OSError` clause.                                          | OPEN   |

### Preflight + resolver gaps (agent: r3-preflight-gaps)

| ID    | Severity | Finding                                                                                                                                                 | Status |
| ----- | -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| R3-P1 | MEDIUM   | `ProviderDirSignal.MIXED` never returned by any collector. Enum member, resolver rules, and doctor all reference it but no code produces it. Dead code. | OPEN   |
| R3-P2 | MEDIUM   | 14 `(signal, action)` pairs fall through to catch-all `logger.warning("Unhandled signal")`. Most benign but should be explicit no-ops.                  | OPEN   |
| R3-P3 | MEDIUM   | CORRUPTED+sync preflight says "repairing" but no repair executes. Sync then produces 0 files with misleading "source dirs empty" warning.               | OPEN   |
| R3-P4 | LOW      | `scope="sync"` skips content integrity. Sync preflight cannot warn about diverged files. By design but limits preflight value.                          | OPEN   |

### Test coverage gaps (agent: r3-test-gaps)

Top 5 most dangerous untested scenarios:

| Priority | Scenario                                                | Risk                    |
| -------- | ------------------------------------------------------- | ----------------------- |
| 1        | Shared-dir protection on per-provider uninstall         | Data loss if regression |
| 2        | Gitignore opt-out detection during sync                 | User intent violated    |
| 3        | `keep_vault=True` actually preserves `.vault/` contents | Documentation loss      |
| 4        | `_resolve_version_warning` + `_parse_version_tuple`     | Preflight crash         |
| 5        | `sync_provider` with `--skip` parameter                 | Wrong providers synced  |

22 specific untested scenarios cataloged (R2-U1 through R2-U22).
No lifecycle tests exist (install->sync->uninstall->reinstall chains).

## Round 3: Security audit (2 agents, data loss + UX gates)

Focused on destructive operations, --force gating, warning clarity,
and safeguard correctness.

### Destructive operations assessment

16 destructive operations audited across the codebase:

| Operation                               | Force-gated                            | Dry-run | Symlink-safe | User-content-check   | Verdict    |
| --------------------------------------- | -------------------------------------- | ------- | ------------ | -------------------- | ---------- |
| `uninstall all` rmtree on managed dirs  | YES                                    | YES     | NO           | NO                   | NEEDS_GATE |
| `uninstall --remove-vault` on .vault/   | YES (double: --force + --remove-vault) | YES     | NO           | NO                   | NEEDS_GATE |
| `uninstall all` unlink on CLAUDE.md etc | YES                                    | YES     | NO           | NO                   | UNSAFE     |
| `uninstall all` unlink on .mcp.json     | YES                                    | YES     | NO           | NO                   | UNSAFE     |
| `uninstall` per-provider rmtree         | YES                                    | YES     | NO           | PARTIAL (shared-dir) | NEEDS_GATE |
| `sync --force` prune stale files        | YES                                    | YES     | NO           | PARTIAL (.md filter) | NEEDS_GATE |
| `sync` overwrite synced rules           | NO                                     | YES     | NO           | NO                   | NEEDS_GATE |
| `sync --force` overwrite system files   | YES                                    | YES     | NO           | YES (vaultspec tag)  | SAFE       |
| `sync` config managed block upsert      | PARTIAL                                | YES     | NO           | YES (block markers)  | SAFE       |
| gitignore block insertion               | NO                                     | NO      | NO           | YES (markers)        | SAFE       |
| gitignore block removal                 | NO (uninstall path)                    | NO      | NO           | YES (markers)        | SAFE       |
| `resource_remove`                       | YES (force or confirm_fn)              | NO      | NO           | N/A                  | SAFE       |
| `atomic_write`                          | N/A (caller gates)                     | N/A     | NO           | N/A                  | SAFE       |
| `write_manifest_data`                   | N/A (internal)                         | N/A     | NO           | N/A                  | SAFE       |
| `_sync_supporting_files`                | NO                                     | YES     | NO           | NO (content-diff)    | SAFE       |
| `install --force` seed_builtins         | YES                                    | YES     | NO           | NO (has snapshots)   | SAFE       |

Key security findings:

| ID      | Severity | Finding                                                                                                                                                       | Status                                                    |
| ------- | -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------- |
| R3-SEC1 | CRITICAL | `.mcp.json` unconditionally deleted on `uninstall all`, destroying user's other MCP server configs. Should surgically remove only `vaultspec-core` entry.     | OPEN                                                      |
| R3-SEC2 | HIGH     | `sync` (without --force) silently overwrites user edits to synced rule files. No warning, no backup, no detection.                                            | OPEN - by design (source is authoritative) but surprising |
| R3-SEC3 | HIGH     | `sync --force` prune deletes user-created `.md` files in provider dirs that don't match a source. No distinction between vaultspec-managed and user-authored. | OPEN                                                      |
| R3-SEC4 | MEDIUM   | No interactive confirmation for any destructive operation. `--force` is the sole safety mechanism. No "about to delete N files, proceed?" prompt.             | OPEN - by design for CLI tools                            |
| R3-SEC5 | MEDIUM   | `.gitignore` writes not atomic (uses `write_bytes` directly, not `atomic_write`). Low risk but inconsistent with manifest writes.                             | OPEN                                                      |
| R3-SEC6 | MEDIUM   | `_scaffold_mcp_json` skips if `.mcp.json` exists but never merges `vaultspec-core` entry into existing config. User may never get MCP server configured.      | OPEN                                                      |

### Error message UX assessment

36 error/warning paths audited:

| Verdict    | Count | Details                                      |
| ---------- | ----- | -------------------------------------------- |
| CLEAR      | 29    | Well-worded, suggests fix, correct exit code |
| AMBIGUOUS  | 7     | Missing recovery guidance or vague wording   |
| MISLEADING | 0     | None found                                   |

Ambiguous paths requiring improvement:

| ID     | Path                        | Issue                                                    |
| ------ | --------------------------- | -------------------------------------------------------- |
| R3-UX1 | `sync core` rejected        | No hint suggesting `sync all` or `install --upgrade`     |
| R3-UX2 | Provider not installed hint | Uses hardcoded `.` instead of actual target path         |
| R3-UX3 | Builtins deleted warning    | No recovery guidance                                     |
| R3-UX4 | No version baseline warning | No recovery guidance                                     |
| R3-UX5 | Version mismatch warning    | Doesn't suggest upgrading the package                    |
| R3-UX6 | Mixed content conflict      | Doesn't explain which files or what "user content" means |
| R3-UX7 | Doctor "unknown" fallback   | Silent degradation, doesn't show actual signal value     |

## Round 4: Backend production readiness (5 agents)

Full-codebase audit assessing transactional safety, filesystem
atomicity, exception boundaries, concurrency, and overall production
readiness. Scope: entire `src/vaultspec_core/`, not just new feature.

### Transactional safety: MISSING

Zero transaction boundaries, rollback, or compensation in the entire
codebase. Every multi-step operation is a linear sequence of side
effects.

| ID    | Severity | Finding                                                                                                                                                  | Status |
| ----- | -------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| R4-T1 | CRITICAL | `uninstall_run` deletes `.vaultspec/` (manifest) FIRST, before provider dirs. A failure after this point leaves the workspace with no recovery metadata. | OPEN   |
| R4-T2 | HIGH     | `install_run` has 6 sequential phases with no error handling between them. Phase 3 failure leaves phases 1-2 committed with no cleanup.                  | OPEN   |
| R4-T3 | HIGH     | `sync_provider` evaluates 5 sync passes as a plain list literal. If `skills_sync` raises, `rules_sync` already wrote files, remaining syncs never run.   | OPEN   |
| R4-T4 | HIGH     | `seed_builtins` and `snapshot_builtins` write files one by one with no rollback on partial failure.                                                      | OPEN   |
| R4-T5 | MEDIUM   | `_ensure_tool_configs` creates a `tempfile.mkdtemp()` for bootstrap but never cleans it up in a `finally` block.                                         | OPEN   |

### Filesystem mutation inventory: 54 operations audited

| Category                       | Count | Atomic | Backup |
| ------------------------------ | ----- | ------ | ------ |
| Writes via `atomic_write`      | 12    | YES    | NO     |
| Raw `write_text`/`write_bytes` | 18    | NO     | NO     |
| `shutil.rmtree`                | 4     | N/A    | NO     |
| `Path.unlink`                  | 4     | N/A    | NO     |
| `shutil.copy2` / `shutil.move` | 4     | N/A    | NO     |
| `Path.mkdir`                   | 10    | N/A    | N/A    |

| ID     | Severity | Finding                                                                                                                                                                   | Status |
| ------ | -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| R4-FS1 | HIGH     | 18 raw `write_text`/`write_bytes` calls (non-atomic) including vault doc auto-fixes, `.gitignore`, skill supporting files, revert module. Crash truncates target.         | OPEN   |
| R4-FS2 | HIGH     | Vault document auto-fix checks (`dangling.py`, `links.py`, `frontmatter.py`, `references.py`) modify user documents via raw `write_text` with no backup and no atomicity. | OPEN   |
| R4-FS3 | MEDIUM   | `atomic_write` temp file naming not unique per-process. Two concurrent writes use same `.tmp` name, causing corruption.                                                   | OPEN   |
| R4-FS4 | MEDIUM   | `atomic_write` Windows fallback (`copyfile` + `unlink`) is not atomic. Crash between copy and unlink leaves orphaned `.tmp`.                                              | OPEN   |

### Exception safety: 22 broad catches, 4 silent swallows

| ID     | Severity | Finding                                                                                                              | Status |
| ------ | -------- | -------------------------------------------------------------------------------------------------------------------- | ------ |
| R4-EX1 | HIGH     | `resource_show/remove/rename` raise `PermissionError`/`OSError` that escapes all CLI catch blocks as raw tracebacks. | OPEN   |
| R4-EX2 | HIGH     | `vault check/list/stats/graph` commands have no exception handling at all. `OSError` propagates as raw traceback.    | OPEN   |
| R4-EX3 | HIGH     | `sync.py:57` - `except Exception: pass` - total silence on file comparison failure.                                  | OPEN   |
| R4-EX4 | MEDIUM   | `_run_preflight` logs diagnosis failures at DEBUG only - invisible without `--debug`.                                | OPEN   |
| R4-EX5 | MEDIUM   | `config_gen.py:100` - `except Exception: continue` silently skips corrupted config metadata.                         | OPEN   |
| R4-EX6 | MEDIUM   | `TagError`, `WorkspaceError`, `RelatedResolutionError` live outside `VaultSpecError` hierarchy.                      | OPEN   |
| R4-EX7 | LOW      | Duplicate `_handle_error` definition in `spec_cmd.py` (DRY violation).                                               | OPEN   |

### Concurrency: no locking

| ID    | Severity | Finding                                                                                                   | Status |
| ----- | -------- | --------------------------------------------------------------------------------------------------------- | ------ |
| R4-C1 | MEDIUM   | No file locking anywhere. Manifest read-modify-write races possible with concurrent CLI invocations.      | OPEN   |
| R4-C2 | MEDIUM   | `sync_provider` performs up to 3 separate read-modify-write cycles on manifest, widening the race window. | OPEN   |
| R4-C3 | LOW      | Config singleton `_cached_config` not thread-safe (benign race).                                          | OPEN   |

### Production readiness ratings

| Area                    | Rating                                     |
| ----------------------- | ------------------------------------------ |
| Type safety             | PRODUCTION_READY                           |
| Code organization       | PRODUCTION_READY                           |
| Modern Python practices | PRODUCTION_READY                           |
| Configuration           | PRODUCTION_READY                           |
| Test quality            | ADEQUATE (717 tests, no coverage tracking) |
| Logging                 | ADEQUATE                                   |
| Dependency hygiene      | ADEQUATE                                   |
| Transactional safety    | MISSING                                    |
| Filesystem atomicity    | NEEDS_WORK                                 |
| Exception boundaries    | NEEDS_WORK                                 |
| Concurrent access       | NEEDS_WORK                                 |

## Round 5: Silent degradation swarm (5 agents)

Focused audit on error swallowing, return value lies, silent
degradation, and whether errors actually reach the user. Scope:
entire `src/vaultspec_core/`.

### The worst anti-pattern: SyncResult.errors never displayed

The CLI rendering layer in `root.py` iterates `r.warnings` with
bullet points but **never iterates `r.errors`**. Error messages
(e.g. `"some-file.md: Permission denied"`) are appended to
`SyncResult.errors` by the sync engine but silently dropped by
every CLI handler. Only the count appears in `format_summary`
(e.g. `"Rules: 9 added, 1 errors"`). Exit code is always 0
regardless of errors.

### Silent error swallowing inventory

59 `except` clauses audited across entire codebase. No bare
`except:` found. Breakdown:

| Pattern                            | Count | Logged | Silent |
| ---------------------------------- | ----- | ------ | ------ |
| `except Exception: pass`           | 3     | 0      | 3      |
| `except ...: continue`             | 6     | 4      | 2      |
| `except ...: return` (no log)      | 10    | 0      | 10     |
| `except Exception` (broad, logged) | 35    | 33     | 2      |
| `except (specific):`               | 5     | 2      | 3      |

### Critical silent paths (errors never reach user)

| ID    | Severity | Finding                                                                                                                                                                                                         | Status |
| ----- | -------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| R5-S1 | CRITICAL | `SyncResult.errors` messages never displayed by any CLI handler. Only count shown via `format_summary`. Exit code unaffected.                                                                                   | OPEN   |
| R5-S2 | CRITICAL | `fire_hooks()` catches all exceptions at DEBUG level only. Return value of `trigger()` discarded by `sync_provider` caller. Post-sync hook failures completely invisible.                                       | OPEN   |
| R5-S3 | HIGH     | `_run_preflight` logs diagnosis failures at DEBUG only. Entire preflight silently abandoned. Corrupt workspace gets no warning before command proceeds.                                                         | OPEN   |
| R5-S4 | HIGH     | `config_gen.py:100` - `except Exception: continue` with ZERO logging. Silently drops config metadata from malformed source files.                                                                               | OPEN   |
| R5-S5 | HIGH     | `mcp_server/vault_tools.py:172` - `except Exception: entry["body"] = ""`. Feeds empty body to MCP/LLM consumers with ZERO logging. LLM sees empty document.                                                     | OPEN   |
| R5-S6 | HIGH     | `collect_md_resources` / `collect_skills` / `collect_system_parts` skip unparseable source files with `logger.error` + `continue`. No error propagated to SyncResult. Sync appears to succeed with fewer files. | OPEN   |

### Return value lies (functions report success on failure)

| ID    | Severity | The Lie                                                       | The Truth                                | Status |
| ----- | -------- | ------------------------------------------------------------- | ---------------------------------------- | ------ |
| R5-L1 | HIGH     | `cmd_sync` exits 0 with sync errors                           | Files failed to sync                     | OPEN   |
| R5-L2 | HIGH     | `read_manifest_data` returns empty ManifestData on corruption | Manifest is corrupt, not absent          | OPEN   |
| R5-L3 | HIGH     | `ensure_gitignore_block` returns False on write failure       | Write was denied, not "no change needed" | OPEN   |
| R5-L4 | MEDIUM   | `_run_preflight` returns silently on crash                    | Diagnosis itself failed                  | OPEN   |
| R5-L5 | MEDIUM   | `_is_managed` returns False on read error                     | Could not determine ownership            | OPEN   |
| R5-L6 | MEDIUM   | `collect_*` returns MISSING/NO_FILE on OSError                | Item exists but is unreadable            | OPEN   |

### Silent degradation paths

| ID    | Severity | Degradation                                                                                                                                                      | Status |
| ----- | -------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| R5-D1 | HIGH     | Source file parse failure silently shrinks the collection. User has 10 rules but sync only processes 9. Summary shows "9 added" with no hint about the 10th.     | OPEN   |
| R5-D2 | HIGH     | `@include` resolution failure produces `<!-- ERROR: Missing include -->` HTML comment in generated rule. AI tool receives incomplete rules. No sync-level error. | OPEN   |
| R5-D3 | MEDIUM   | Manifest v1.0 silently upgraded to v2.0 on next write. Unknown fields from future v3.0 silently dropped on round-trip.                                           | OPEN   |
| R5-D4 | MEDIUM   | Skill directory without `SKILL.md` completely invisible. No warning during sync.                                                                                 | OPEN   |
| R5-D5 | LOW      | MCP `find` tool falls back to empty rankings on graph failure. MCP client gets valid but impoverished results.                                                   | OPEN   |

## Summary statistics

| Round     | Critical | High   | Medium | Low   | Fixed  | Open          |
| --------- | -------- | ------ | ------ | ----- | ------ | ------------- |
| R1        | 2        | 10     | 10     | 1     | 21     | 2 (by design) |
| R2        | 1        | 4      | 6      | 1     | 0      | 12            |
| R3        | 4        | 7      | 12     | 2     | 0      | 25            |
| R3-Sec    | 1        | 2      | 3      | 0     | 0      | 6             |
| R3-UX     | 0        | 0      | 7      | 0     | 0      | 7             |
| R4        | 1        | 7      | 7      | 1     | 0      | 16            |
| R5        | 2        | 7      | 4      | 1     | 0      | 14            |
| R6        | 0        | 3      | 4      | 2     | 0      | 9             |
| **Total** | **11**   | **40** | **53** | **8** | **21** | **91**        |

## Round 6: Systemic deep-dive (5 agents, final round)

Final audit round targeting systemic issues: data flow integrity,
state invariants, command ordering, cross-provider interference, and
config generation correctness.

### Data flow: SyncResult.errors exit code + agents_sync warnings dropped

| ID     | Severity | Finding                                                                                                                                             | Status |
| ------ | -------- | --------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| R6-DF1 | HIGH     | `cmd_sync` exit code ignores `SyncResult.errors` - always exits 0 even when files failed to sync. Exit code should be non-zero when errors present. | OPEN   |
| R6-DF2 | HIGH     | `agents.py:281-287` `_merge()` is missing `total.warnings.extend(result.warnings)` - agent stale-file warnings silently dropped.                    | OPEN   |

### State invariants: path traversal + TOCTOU

| ID     | Severity | Finding                                                                                                                                                                                                                       | Status |
| ------ | -------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| R6-SI1 | HIGH     | Tool directories not validated as descendants of workspace root. A malicious config with `gemini_dir = "../../etc/evil"` could cause sync to write files or uninstall to rmtree outside workspace. No path containment check. | OPEN   |
| R6-SI2 | MEDIUM   | `_sync_supporting_files` crashes on `FileNotFoundError` if source file deleted between enumeration and read (TOCTOU). `collect_md_resources` handles this gracefully but supporting files do not.                             | OPEN   |
| R6-SI3 | MEDIUM   | Phantom manifest entries block shared-dir uninstall. Manual deletion of `.claude/` leaves it in manifest; `providers_sharing_dir` counts it as still sharing.                                                                 | OPEN   |
| R6-SI4 | LOW      | `SyncResult` counts exclude errored files. `added + updated + skipped + pruned` undercounts by error count. No consumer relies on totals.                                                                                     | OPEN   |
| R6-SI5 | LOW      | Shared dir double-sync inflates `skipped` count when gemini + antigravity both sync to `.agents/skills/`. Functionally benign.                                                                                                | OPEN   |

### Config generation: circular includes + TagError crash

| ID     | Severity | Finding                                                                                                                                                                                         | Status |
| ------ | -------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| R6-CG1 | MEDIUM   | `resolve_includes` has no circular include guard. File A including file B including file A causes `RecursionError` (stack overflow).                                                            | OPEN   |
| R6-CG2 | MEDIUM   | `_sync_managed_md` does not catch `TagError` from `upsert_block`. Broken tags in `CLAUDE.md`/`GEMINI.md` crash sync instead of skipping gracefully. The TOML path handles this but MD does not. | OPEN   |

### Command ordering: confirmed correct

No ordering bugs found. Key invariants verified:

- `.vaultspec/` created before `resolve_workspace`/`init_paths`
- `add_providers` (manifest) runs before `sync_provider`
- Manifest v2 metadata written last (crash-safe)
- Config sync deduplicates shared files (GEMINI.md, AGENTS.md)
- Context isolation via `contextvars.copy_context()` is correct

---
tags:
  - '#plan'
  - '#audit-findings'
date: '2026-03-30'
related:
  - '[[2026-03-27-cli-ambiguous-states-audit]]'
  - '[[2026-03-27-cli-ambiguous-states-resolver-adr]]'
  - '[[2026-03-27-cli-ambiguous-states-gitignore-adr]]'
  - '[[2026-03-28-cli-ambiguous-states-audit-fixes-plan]]'
---

# `audit-findings` plan

Comprehensive triage and phased execution plan for all 91 open
findings from the `cli-ambiguous-states` rolling audit (6 rounds).
Supersedes the earlier 12-fix plan with full coverage of R2-R6
findings. Deduplicated by root cause - many audit IDs across rounds
describe the same underlying defect. Organized into 5 execution
phases ordered by risk (data loss first, then visibility, then
correctness, then hardening, then coverage).

## Proposed Changes

The audit surfaced 91 open findings across 6 rounds. After
deduplication, these collapse to approximately 30 distinct root
causes. Each root cause maps to a concrete fix. Fixes are grouped
into dependency-ordered phases so that data-safety and
error-visibility improvements land before logic fixes that depend
on those foundations.

Phases 1-3 are the core fixes (high-value, bounded scope). Phase 4
is production hardening (broader scope, lower urgency). Phase 5 is
test coverage gap closure. Phase 6 covers security and path safety.
Phase 7 is systemic filesystem hardening. Phase 8 is completeness
and UX polish. Every open finding is addressed - nothing is deferred.
Only 6 findings are acknowledged as by-design (not defects).

## Tasks

- Phase 1: Data safety (prevents data loss and destructive side effects)

  1. Add `_rmtree_robust()` helper to `core/helpers.py`. Must check
     `is_symlink()` before rmtree (unlink symlink instead of following
     into target), and pass `onerror` handler that clears NTFS
     read-only attribute on Windows. Replace all 4 production
     `shutil.rmtree` calls in `commands.py`, `sync.py`, `resources.py`.
     Also guard `ensure_dir()` against creating directories inside
     symlink targets.
     Fixes: R2-D1, R2-D2, R3-S1, R3-S3, R3-S4, R2-W1, R2-W2.

  1. Implement surgical `.mcp.json` handling. In `uninstall_run`,
     remove only the `vaultspec-core` key from `mcpServers`, preserve
     all user entries. Delete the file only when no servers remain.
     Fix `_scaffold_mcp_json` to merge `vaultspec-core` entry into
     an existing `.mcp.json` rather than skipping when the file exists.
     Fixes: R2-D3, R3-M1, R3-SEC1, R3-M2, R3-SEC6.

  1. Fix `gitignore_managed` flag on idempotent re-install. In
     `install_run`, set `gitignore_managed = True` when the managed
     block already exists (check for marker presence in file content),
     not just when `ensure_gitignore_block` returns True.
     Fixes: R2-B1, R3-F1.

  1. Reorder uninstall to delete `.vaultspec/` LAST. Provider dirs
     and files first, manifest update after each provider removal,
     framework directory last. Wrap each deletion in try/except to
     collect errors and continue (best-effort teardown). This ensures
     manifest remains available as recovery metadata if a mid-way
     failure occurs.
     Fixes: R4-T1, R3-S2.

- Phase 2: Error visibility (errors reach the user)

  1. Display `SyncResult.errors` in CLI handlers. In `cmd_sync`
     (and any other CLI handler that processes `SyncResult`), iterate
     `r.errors` alongside `r.warnings` in the rendering output. Set
     exit code to 1 when any errors are present.
     Fixes: R5-S1, R5-L1, R6-DF1.

  1. Fix `agents.py` `_merge()` to propagate warnings. Add
     `total.warnings.extend(result.warnings)` in the merge loop.
     Fixes: R6-DF2.

  1. Add `except OSError` clause to `cmd_install`, `cmd_uninstall`,
     `cmd_sync` in `root.py`. Convert filesystem errors to clean CLI
     messages instead of raw Python tracebacks. Also add `.vaultspec`
     is-file guard (if path exists but `is_dir()` is False, emit
     clear error and exit).
     Fixes: R2-E1, R2-E2, R3-M3, R3-M4.

  1. Elevate `_run_preflight` failure logging from DEBUG to WARNING.
     When diagnosis itself crashes, the user must be informed that
     preflight was skipped rather than silently proceeding.
     Fixes: R5-S3, R5-L4, R4-EX4.

  1. Fix silent catches across the codebase:

     - `config_gen.py:100`: narrow to specific exception, add
       `logger.warning` with the file path and error.
     - `sync.py:57`: narrow `except Exception` to `except OSError`,
       add `logger.debug` with context.
     - `mcp_server/vault_tools.py:172`: add `logger.warning` when
       body read fails so MCP consumers are aware of empty documents.
       Fixes: R5-S4, R5-S5, R4-EX3, R4-EX5.

  1. Elevate `fire_hooks()` failure logging. Hook trigger failures
     caught at DEBUG should be at WARNING. Ensure the return value
     of `trigger()` is checked by `sync_provider` caller and any
     failures are appended to `SyncResult.warnings`.
     Fixes: R5-S2.

  1. Propagate source parse failures to `SyncResult`. When
     `collect_md_resources`, `collect_skills`, or
     `collect_system_parts` skip an unparseable source file, append
     a warning to `SyncResult.warnings` (not just `logger.error`).
     The sync summary must reflect the discrepancy.
     Fixes: R5-S6, R5-D1.

  1. Propagate `@include` resolution failures. When
     `resolve_includes` encounters a missing include, append a
     warning to `SyncResult.warnings` instead of (or in addition to)
     embedding an HTML comment in the output. The sync summary must
     surface that the generated rule is incomplete.
     Fixes: R5-D2.

- Phase 3: Flag precedence and logic fixes

  1. Fix `install --upgrade --dry-run` flag precedence. Check
     `upgrade` before `dry_run` in `install_run`. When both flags
     are set, show the upgrade-specific preview (which files would
     change) rather than the generic dry-run output.
     Fixes: R2-B2, R3-F2.

  1. Guard `install --skip core` when `.vaultspec/` absent. Emit a
     clear error ("cannot sync providers without framework; remove
     --skip core or run install first") instead of crashing during
     the sync phase.
     Fixes: R2-B3, R3-F3.

  1. Wrap sync passes in `sync_provider` with individual try/except.
     Each of the 5 sync passes (rules, skills, agents, supporting
     files, config) catches exceptions independently so one failure
     does not prevent the others. Accumulate errors in
     `SyncResult.errors`.
     Fixes: R4-T3.

  1. Add error handling between `install_run` phases. Wrap phases
     2-6 in try/except so that a failure in e.g. phase 3 does not
     leave phases 1-2 committed with no cleanup. Collect errors and
     report all failures at the end. Do not attempt rollback (too
     complex for this phase) but ensure the user sees what failed.
     Fixes: R4-T2.

  1. Fix `ensure_gitignore_block` return value semantics. On write
     failure (e.g. `PermissionError`), raise the exception rather
     than returning False (which the caller interprets as "no change
     needed"). This prevents the lie where a failed write looks like
     a no-op.
     Fixes: R5-L3.

  1. Fix `read_manifest_data` corruption handling. When the manifest
     file exists but contains invalid JSON or an unexpected schema,
     raise `VaultSpecError` (or a subclass) instead of returning an
     empty `ManifestData`. Callers that need graceful degradation
     can catch explicitly.
     Fixes: R5-L2.

  1. Fix `_is_managed` read error handling. On `OSError`, raise
     rather than returning False. The caller must distinguish
     "not managed" from "could not determine".
     Fixes: R5-L5.

  1. Fix CORRUPTED+sync preflight messaging. When preflight detects
     CORRUPTED and emits "repairing", ensure the repair actually
     executes (call `write_manifest_data` with a valid empty
     manifest) before proceeding to sync. If repair cannot execute,
     error instead of silently continuing.
     Fixes: R3-P3.

- Phase 4: Exception boundaries and production hardening

  1. Add exception handling to resource commands. Wrap
     `resource_show`, `resource_remove`, `resource_rename` CLI
     entry points with `except OSError` to catch `PermissionError`
     and other filesystem errors. Convert to clean CLI messages.
     Fixes: R4-EX1.

  1. Add exception handling to vault commands. Wrap `vault check`,
     `vault list`, `vault stats`, `vault graph` CLI entry points
     with `except (OSError, VaultSpecError)`. Convert to clean CLI
     messages with appropriate exit codes.
     Fixes: R4-EX2.

  1. Deduplicate `_handle_error` in `spec_cmd.py`. Collapse the two
     identical definitions into one.
     Fixes: R4-EX7.

  1. Clean up temp dir in `_ensure_tool_configs`. Add `finally`
     block to remove the `tempfile.mkdtemp()` directory after
     bootstrap completes.
     Fixes: R4-T5.

  1. Add error collection to `seed_builtins` and
     `snapshot_builtins`. Instead of aborting on first failure,
     collect errors per file and continue. Return the error list
     to the caller for reporting.
     Fixes: R4-T4.

  1. Fix `atomic_write` temp file naming. Use a unique suffix
     per-process (e.g. PID + counter or `uuid4().hex[:8]`) to
     prevent collision when two concurrent processes write the same
     target.
     Fixes: R4-FS3.

  1. Harden `atomic_write` Windows fallback. When the
     `copyfile + unlink` fallback is used, ensure the `.tmp` file
     is cleaned up in a `finally` block even if the process crashes
     between copy and unlink.
     Fixes: R4-FS4.

  1. Make `.gitignore` writes atomic. Use `atomic_write` for
     `.gitignore` modifications in `ensure_gitignore_block` instead
     of raw `write_bytes`. This is consistent with manifest writes.
     Fixes: R3-SEC5.

  1. Handle TOCTOU in `_sync_supporting_files`. Add
     `except FileNotFoundError` around source file reads so that a
     file deleted between enumeration and read does not crash the
     entire sync pass.
     Fixes: R6-SI2.

  1. Catch `TagError` in `_sync_managed_md`. The TOML path already
     handles this but the MD path does not. Catch `TagError` from
     `upsert_block` and append to `SyncResult.errors` instead of
     crashing.
     Fixes: R6-CG2.

  1. Fix `collect_*` return value on `OSError`. When a collector
     cannot read a file due to permissions, return a distinct signal
     (or raise) rather than returning `MISSING`/`NO_FILE` which
     falsely indicates the item does not exist.
     Fixes: R5-L6.

  1. Fix phantom manifest entries blocking shared-dir uninstall.
     When `providers_sharing_dir` counts sharing providers, validate
     that each provider's directory actually exists on disk before
     counting it as still sharing.
     Fixes: R6-SI3.

- Phase 5: Test coverage gap closure

  1. Add tests for `_rmtree_robust` covering: symlinked directory,
     Windows read-only file, error collection, partial failure.

  1. Add tests for surgical `.mcp.json` removal: pre-existing user
     entries preserved, file deleted only when empty, merge into
     existing config.

  1. Add tests for `SyncResult.errors` display: errors rendered in
     output, exit code is 1 when errors present.

  1. Add tests for the 22 untested scenarios cataloged in the audit
     (R2-U1 through R2-U22). Priority order:

     - R2-U16: shared-dir protection on per-provider uninstall
     - R2-U11: gitignore opt-out detection during sync
     - R2-U19-U22: lifecycle chains (install, modify, sync, uninstall,
       reinstall)
     - R2-U1-U10: install/sync flag combinations
     - R2-U13-U15: uninstall flag combinations
     - R2-U17-U18: doctor edge cases

  1. Add lifecycle integration tests that chain install, sync,
     uninstall, and reinstall operations to verify end-to-end
     invariants across command boundaries.

- Phase 6: Security and path safety

  1. Add path containment validation. Validate that all tool
     directories resolved from config are descendants of the
     workspace root. In `init_paths` or at config load time, resolve
     each configured directory to its absolute path and assert it is
     within the workspace root using `Path.resolve()` and
     `is_relative_to()`. Raise `VaultSpecError` if a path escapes
     (e.g. `gemini_dir = "../../etc/evil"`). Apply the same check
     in `sync_provider` and `uninstall_run` before any rmtree or
     write operations.
     Fixes: R6-SI1.

  1. Add content-ownership heuristic for `sync --force` prune.
     Before pruning a `.md` file in a provider directory, check
     whether it was created by vaultspec (present in the source
     collection or carries the `AUTO-GENERATED` marker) or is
     user-authored. Only prune vaultspec-managed files. User-authored
     files should be left in place with a warning. The heuristic:
     a file is managed if (a) it has a matching source in
     `.vaultspec/rules/` or (b) it contains the `AUTO-GENERATED`
     marker. Otherwise it is user content.
     Fixes: R3-SEC3.

  1. Unify exception hierarchy under `VaultSpecError`. Move
     `TagError`, `WorkspaceError`, and `RelatedResolutionError` to
     inherit from `VaultSpecError` (or a shared base). Update all
     except clauses that catch these individually to also catch via
     the base class. This enables CLI-level `except VaultSpecError`
     to cover all framework errors uniformly.
     Fixes: R4-EX6.

- Phase 7: Systemic filesystem hardening

  1. Migrate raw `write_text`/`write_bytes` calls to `atomic_write`.
     Audit all 18 raw write calls identified in R4-FS1. For each,
     determine whether atomicity matters (writes to user-visible
     files, config files, manifest). Migrate those where a mid-write
     crash would leave a corrupted file. Leave writes where atomicity
     is irrelevant (e.g. temp files, log output) unchanged. Document
     the rationale for each decision.
     Fixes: R4-FS1.

  1. Add backup-before-write to vault document auto-fix checks.
     In `dangling.py`, `links.py`, `frontmatter.py`, `references.py`,
     before modifying a user document, write a `.bak` copy alongside
     it. If the write succeeds, remove the `.bak`. If it fails, the
     `.bak` remains as recovery. Use `atomic_write` for the modified
     content.
     Fixes: R4-FS2.

  1. Add advisory file locking to manifest read-modify-write. Use
     `fcntl.flock` (Unix) / `msvcrt.locking` (Windows) around the
     manifest read-modify-write cycle in `write_manifest_data`. The
     lock is advisory (cooperative) - it prevents concurrent CLI
     invocations from racing on the manifest. The serial counter
     remains as a secondary detection mechanism.
     Fixes: R4-C1, R4-C2, R2-W4.

  1. Add circular include guard to `resolve_includes`. Maintain a
     `visited: set[Path]` parameter (defaulting to empty) that
     tracks files already in the include chain. If a file appears
     in `visited`, emit a warning and return the raw include
     directive as-is instead of recursing. This prevents
     `RecursionError` on `A includes B includes A` cycles.
     Fixes: R6-CG1.

- Phase 8: Completeness and UX polish

  1. Implement or remove `ProviderDirSignal.MIXED`. Either wire a
     collector to actually produce the MIXED signal (detect
     non-vaultspec content in provider dirs) or remove the dead enum
     member, its resolver rules, and its doctor handling. Prefer
     implementation: the collector should flag directories containing
     files that don't match any known resource pattern (not .md rules,
     not skill dirs, not config files).
     Fixes: R1-M2, R3-P1.

  1. Fix `doctor --target /nonexistent` error message. Check
     `target.exists()` before running diagnosis. If the path does not
     exist, emit "target directory does not exist: /nonexistent"
     instead of "framework missing".
     Fixes: R2-E3.

  1. Fix `atomic_write` line ending handling. Use binary-mode write
     (`write_bytes`) instead of text-mode `write_text` to prevent
     silent `\n` to `\r\n` conversion on Windows. Callers that need
     platform line endings must convert explicitly.
     Fixes: R2-W3.

  1. Fix preflight messaging for phased resolution. When preflight
     displays steps as "will repair" that are deferred to a later
     phase, change the wording to "detected (will be addressed by
     `command`)" so the user understands the repair is not immediate.
     Fixes: R2-B4, R3-F4.

  1. Add explicit no-op handling for 14 `(signal, action)` pairs
     in the resolver. Replace the catch-all `logger.warning ("Unhandled signal")` with explicit match arms that either
     document why no action is needed or emit a specific diagnostic.
     Fixes: R3-P2.

  1. Add thread-safety to config singleton. Use `threading.Lock`
     around `_cached_config` read-modify in the config loader. While
     the CLI is single-threaded, the MCP server may serve concurrent
     requests.
     Fixes: R4-C3.

  1. Warn on skill directories without `SKILL.md`. During sync,
     when iterating skill directories in `.vaultspec/rules/skills/`,
     if a directory lacks `SKILL.md`, append a warning to
     `SyncResult.warnings` identifying the directory.
     Fixes: R5-D4.

  1. Improve MCP `find` tool graph-failure fallback. When the vault
     graph fails to load, log a warning (not just silently return
     empty rankings) and include a note in the MCP response that
     ranking is unavailable.
     Fixes: R5-D5.

  1. Fix `SyncResult` counts to include errored files. When a file
     errors during sync, increment an explicit `errored` counter.
     The summary line should read e.g. "9 added, 1 errored" rather
     than silently omitting the errored file from all counts.
     Fixes: R6-SI4.

  1. Fix shared-dir double-sync `skipped` inflation. When multiple
     providers share a directory (e.g. `.agents/skills/`), track
     which files have already been synced in the current invocation
     and skip the duplicate without incrementing the `skipped`
     counter.
     Fixes: R6-SI5.

  1. Improve 7 ambiguous error/warning messages:

     - R3-UX1: `sync core` rejection - add hint suggesting
       `sync all` or `install --upgrade`.
     - R3-UX2: provider not installed hint - use actual target path
       instead of hardcoded `.`.
     - R3-UX3: builtins deleted warning - add recovery guidance
       ("run install --upgrade to restore").
     - R3-UX4: no version baseline warning - add recovery guidance
       ("run install --upgrade to establish baseline").
     - R3-UX5: version mismatch warning - suggest upgrading the
       package ("pip install --upgrade vaultspec-core").
     - R3-UX6: mixed content conflict - list the specific files
       and explain what "user content" means.
     - R3-UX7: doctor "unknown" fallback - show the actual signal
       value instead of "unknown".
       Fixes: R3-UX1, R3-UX2, R3-UX3, R3-UX4, R3-UX5, R3-UX6,
       R3-UX7.

## Acknowledged by-design findings (not defects)

These findings describe intentional behavior documented in the ADRs.
They are not bugs and require no fix:

- R1-W4 (LOW): `Literal` type annotation is sufficient for the
  state parameter. No enum needed.
- R1-M6 (MEDIUM): `ContentSignal.DIVERGED` exists for future
  SHA-256 content comparison. Unreachable by design until that
  feature ships.
- R3-SEC2 (HIGH): `sync` overwrites user edits. Source is
  authoritative by design per the resolver ADR.
- R3-SEC4 (MEDIUM): no interactive confirmation. `--force` is the
  designed safety mechanism for CLI tools.
- R3-P4 (LOW): `scope="sync"` skips content integrity. By design
  - content integrity is expensive and only runs for `doctor`.
- R5-D3 (MEDIUM): manifest v1.0 silently upgraded to v2.0. By
  design per the resolver ADR.

## Parallelization

- Phases 1 and 2 have no internal dependencies and could be
  executed by parallel sub-agents if resources allow. Phase 1 tasks
  are independent of each other. Phase 2 tasks are mostly
  independent except task 2.1 (SyncResult.errors display) should
  land before task 2.7 (collect\_\* error propagation) since the
  latter adds errors that the former must render.

- Phase 3 depends on Phase 2 being complete (error collection
  patterns established in Phase 2 are reused in Phase 3).

- Phase 4 is largely independent of Phases 1-3 and could run in
  parallel, but benefits from Phase 2's exception handling patterns.

- Phase 5 depends on all prior phases (tests validate the fixes).

- Phase 6 depends on Phase 4 (exception hierarchy from 6.3 builds
  on Phase 4's exception boundary work; path containment from 6.1
  builds on Phase 1's rmtree hardening).

- Phase 7 depends on Phase 4 (atomic_write improvements from Phase
  4 must land before the systemic migration in 7.1).

- Phase 8 is largely independent and can overlap with Phases 6-7.
  UX polish (8.11) has no code dependencies.

Recommended execution order: Phase 1, Phase 2, Phase 3, Phase 4,
Phase 5, then Phase 6 + Phase 8 in parallel, Phase 7 last.

## Verification

- All existing 598+ tests must pass after each phase.
- Pre-commit hooks must pass after each phase.
- Phase 1 verification: create a symlinked provider directory and
  run uninstall - must unlink, not follow. Create a `.mcp.json`
  with user entries and run uninstall - user entries must survive.
- Phase 2 verification: introduce a deliberate sync error (e.g.
  read-only target file) and confirm the error message appears in
  CLI output and exit code is non-zero.
- Phase 3 verification: run `install --upgrade --dry-run` and
  confirm upgrade preview is shown. Run `install --skip core`
  without `.vaultspec/` and confirm clear error.
- Phase 4 verification: run `vault check` on a workspace with
  permission-denied files and confirm clean error message instead
  of traceback.
- Phase 5 verification: all new tests pass. No mocks, stubs, or
  skips. Real filesystem assertions using `WorkspaceFactory`.
- Phase 6 verification: configure a tool directory with `../`
  traversal and confirm it is rejected. Run `sync --force` prune
  on a directory with user-authored .md files and confirm they
  survive. Verify all custom exceptions inherit from
  `VaultSpecError`.
- Phase 7 verification: grep for raw `write_text`/`write_bytes`
  calls and confirm only documented exceptions remain. Test
  concurrent CLI invocations and confirm manifest locking prevents
  corruption. Test `A includes B includes A` and confirm no
  `RecursionError`.
- Phase 8 verification: run `doctor --target /nonexistent` and
  confirm clear message. Run sync with a skill dir lacking
  `SKILL.md` and confirm warning. Verify all 7 UX messages are
  improved per the audit descriptions. Verify `SyncResult` counts
  are accurate including errored files.

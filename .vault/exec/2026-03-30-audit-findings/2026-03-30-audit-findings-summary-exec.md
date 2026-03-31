---
tags:
  - '#exec'
  - '#audit-findings'
date: '2026-03-30'
related:
  - '[[2026-03-30-audit-findings-plan]]'
  - '[[2026-03-27-cli-ambiguous-states-audit]]'
  - '[[2026-03-27-cli-ambiguous-states-resolver-adr]]'
  - '[[2026-03-27-cli-ambiguous-states-gitignore-adr]]'
---

# `audit-findings` summary

Complete resolution of all 91 open findings from the
`cli-ambiguous-states` rolling audit across 6 rounds.
8 execution phases, 0 deferrals. Only 6 findings acknowledged
as by-design (not defects).

## Description

The audit identified 91 open findings across categories: data
loss risks, silent degradation, exception boundaries, transaction
safety, filesystem atomicity, concurrency, security, flag bugs,
return value lies, and UX gaps. After deduplication by root cause,
these collapsed to approximately 50 distinct fixes.

Prior work (PR #18, commits 68b882a, 6e42663) had already
addressed roughly half of the phases 1-3 items. This execution
completed all remaining items and extended coverage to the
formerly-deferred phases 6-8.

Key outcomes:

- All `shutil.rmtree` calls use `_rmtree_robust` with symlink
  and Windows hardening
- `.mcp.json` surgical removal preserves user MCP entries
- `SyncResult.errors` displayed in CLI with non-zero exit code
- Parse failures and @include errors propagated to SyncResult
- All collector/hook logging elevated to appropriate levels
- `atomic_write` uses unique temp names and binary mode
- Advisory file locking on manifest read-modify-write
- Path containment validation prevents directory traversal
- Content-ownership heuristic prevents pruning user files
- Exception hierarchy unified under `VaultSpecError`
- Backup-before-write for vault document auto-fixes
- Circular include guard prevents `RecursionError`
- Thread-safe config singleton for MCP concurrency
- `ProviderDirSignal.MIXED` now detectable
- All 7 UX messages improved with recovery guidance
- 26 new tests covering all 22 previously untested scenarios
- 1 real bug discovered and fixed (gitignore opt-out dead code)

## Tests

706 tests pass (680 existing + 26 new). All pre-commit hooks
pass. No mocks, stubs, patches, or skips.

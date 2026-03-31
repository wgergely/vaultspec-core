---
tags:
  - '#exec'
  - '#audit-findings'
date: '2026-03-30'
related:
  - '[[2026-03-30-audit-findings-plan]]'
  - '[[2026-03-27-cli-ambiguous-states-audit]]'
---

# `audit-findings` phase 5 exec

Test coverage gap closure. Added 26 new tests covering all 22
untested scenarios from the audit (R2-U1 through R2-U22), plus
fix validation tests and a full lifecycle integration test. Also
fixed a real bug discovered during test writing.

- Created: `src/vaultspec_core/tests/cli/test_audit_coverage.py`
- Modified: `src/vaultspec_core/core/commands.py`

## Description

26 tests organized by priority:

- Shared-dir protection (R2-U16): 3 tests verifying `.agents/`
  survives per-provider uninstall when other providers share it.
- Gitignore opt-out detection (R2-U11): 1 test verifying sync
  respects user-removed gitignore block and sets managed=False.
- Lifecycle chains (R2-U19-U22): 4 tests for additive install,
  reinstall, self-heal, and late gitignore creation.
- Install/sync flags (R2-U1, U2, U5, U6, U7, U8, U10): 7 tests
  covering core-only install, single provider, invalid provider,
  mcp.json merge, single sync, dry-run+force, uninstalled sync.
- Uninstall combinations (R2-U13, U15): 2 tests for single
  provider uninstall and uninstall-when-not-installed.
- Doctor edge cases (R2-U17, U18): 3 tests for JSON schema and
  v1.0 manifest handling.
- Fix validation: 5 tests for `_rmtree_robust` symlink safety,
  surgical `.mcp.json` removal, and `SyncResult.errors` display.
- Full lifecycle integration: 1 test chaining install, sync,
  selective uninstall, verify, reinstall, verify.

Bug fix discovered during testing: gitignore opt-out detection in
`sync_provider` was dead code. The old code called
`ensure_gitignore_block` (which recreated the block) before
checking if the user removed it. Fixed to check block presence
first, then only call ensure if block still exists.

## Tests

All 706 tests pass (680 existing + 26 new). No mocks, stubs,
patches, or skips. All tests use `WorkspaceFactory` for real
filesystem assertions.

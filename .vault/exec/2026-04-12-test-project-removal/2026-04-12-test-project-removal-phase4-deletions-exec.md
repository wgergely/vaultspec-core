---
tags:
  - '#exec'
  - '#test-project-removal'
date: 2026-04-12
related:
  - '[[2026-04-12-test-project-removal-plan]]'
---

# `test-project-removal` `phase4` `deletions`

Phase 4 executes the issue `#67` housekeeping deletions in a single batch.

- Deleted: `test-project/` (474 files)
- Deleted: `rsc/svg/vaultspec-agent-err.svg`, `rsc/svg/vaultspec-agent-ok.svg`, `rsc/svg/vaultspec-agent-stroll.svg`
- Deleted: `.geminiignore` (0 bytes)
- Deleted: `extension.toml`
- Modified: `.gitignore`
- Modified: `.pre-commit-config.yaml`
- Modified: `.dockerignore`

## Description

The four `git rm` operations were issued in one shell call after the Phase 3 cross-tree sweep confirmed no test still imports `TEST_PROJECT`, `TEST_VAULT`, or any `test-project` path. `.gitignore` lines 187-189 (the `test-project/*` exclusion block) were replaced with a single defensive `test-project/` line so a stray local checkout never re-enters the index. `.pre-commit-config.yaml` lost both `exclude: ^test-project/` lines from the `mdformat-check` and `pymarkdown` hooks. `.dockerignore` lost the bare `test-project` entry on line 10. A stale comment in `src/vaultspec_core/vaultcore/checks/tests/test_index_safety.py` referencing the historical corpus was tightened to remove the `test-project` mention.

## Tests

No new tests in this phase. Verification deferred to the Phase 5 validation gate which runs the full pytest suite, ruff, ty, and the hygiene grep set.

---
tags:
  - '#exec'
  - '#protocol-stack'
date: '2026-02-22'
related:
  - '[[2026-02-22-protocol-stack-deep-audit-plan]]'
---

# `protocol-stack` Track D `Steps 4a-4b`

Added missing `__init__.py` and removed `monkeypatch.chdir`.

- Created: `src/vaultspec/tests/__init__.py`
- Modified: `src/vaultspec/orchestration/utils.py`
- Modified: `src/vaultspec/orchestration/tests/test_utils.py`

## Description

**Step 4a:** Created empty `src/vaultspec/tests/__init__.py` to fix Python
package discovery. Child `src/vaultspec/tests/cli/__init__.py` already
existed.

**Step 4b:** Refactored `find_project_root()` to accept an optional
`start_dir: pathlib.Path | None = None` parameter (defaults to
`Path.cwd()`). Updated `TestFindProjectRoot.test_finds_git_root` to pass
`TEST_PROJECT` directly via the new parameter, eliminating the banned
`monkeypatch.chdir` call.

## Tests

Grep confirmed no other callers of `find_project_root()` — the default
`Path.cwd()` behavior is preserved for all existing call sites.

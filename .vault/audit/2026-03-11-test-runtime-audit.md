---
tags:
  - '#audit'
  - '#test-runtime'
date: 2026-03-11
---

# Test Runtime Audit

## Scope

Audit and repair of the failing pytest suite after the `vaultspec-core` naming
and documentation refactor.

## Root Causes

### 1. Stale tests against the current hooks and hydration contracts

- `src/vaultspec_core/hooks/tests/test_hooks.py` still expected the removed
  `vault.index.updated` event.

- `src/vaultspec_core/vaultcore/tests/test_hydration.py` still exercised an old
  hydration signature and old placeholder syntax.

These were straightforward stale-test failures caused by runtime drift.

### 2. Windows temp-path compatibility shim only applied to `tests/`

- The Python test suites under `src/.../tests` did not inherit
  `tests/conftest.py`.

- As a result, `tmp_path` setup for those suites still used the shared OS temp
  root and hit `.lock` permission failures under
  `C:\Users\hello\AppData\Local\Temp\pytest-of-hello`.

This was a harness-scoping defect, not a product defect.

### 3. Mutation-heavy tests were running on a filesystem that rejects normal

file replacement and deletion

- The initial repo-local pytest temp root lived on `Y:`.

- On this filesystem, plain `os.replace(...)`, `Path.rename(...)`, and
  `Path.unlink(...)` on freshly written temp files failed with `WinError 5`.

- That caused broad false failures in:

  - atomic write tests
  - sync tests that prune or replace files
  - verification repair tests that rename documents
  - MCP tests that create vault documents

This was an execution-environment constraint, not a logic regression in the
application code.

## Repairs Applied

- Updated stale hook-event and hydration tests to match the live runtime.

- Extracted the Windows temp compatibility logic into
  `tests/_windows_temp_compat.py`.

- Added repo-root `conftest.py` so all test trees inherit the same temp-path
  compatibility layer.

- Moved the pytest temp root to a dedicated standard Windows temp subdirectory
  under `%TEMP%`, which is writable and supports rename/delete semantics
  required by the suite without hard-coding a tool-workspace path.

## Verification

- `uv sync` completed successfully after escalation.
- Full suite result:
  - `333 passed`
  - `1 warning`
  - runtime: `7.82s`

## Residual Warnings

### Pytest cache path on `Y:`

- `.pytest_cache` creation still warns with `WinError 5` because the repository
  filesystem does not allow the cache provider to create its cache tree there.

- The suite still passes because cache writes are non-critical.

This residual warning should be treated as an environment/runtime note rather
than evidence of failing product behavior.

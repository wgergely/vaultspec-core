---
tags:
  - '#exec'
  - '#test-project-removal'
date: 2026-04-12
related:
  - '[[2026-04-12-test-project-removal-plan]]'
---

# `test-project-removal` `phase-3` `cli-modules`

Migrated four CLI test modules from the deleted `test_project` / `_TEST_PROJECT_SRC` fixture
to the `synthetic_project` fixture defined in `conftest.py` (Phase 2).

- Modified: `src/vaultspec_core/tests/cli/test_cli_live.py`
- Modified: `src/vaultspec_core/tests/cli/test_integration.py`
- Modified: `src/vaultspec_core/tests/cli/test_main_cli.py`
- Modified: `src/vaultspec_core/tests/cli/test_collectors.py`

## Description

- `test_cli_live.py`: Removed inline `_TEST_PROJECT_SRC` constant (pointing at `test-project/`)
  and the local `project` fixture that used `shutil.copytree`. Renamed every `project` fixture
  parameter across all 50+ test functions and class methods to `synthetic_project`. Removed
  the now-unused `shutil` and `pathlib.Path` imports. Fixed all E501 line-length violations
  introduced by the longer parameter name.

- `test_integration.py`: Renamed two `test_project` fixture parameters to `synthetic_project`.
  Updated inline comment referencing `test-project`.

- `test_main_cli.py`: Renamed eleven `test_project` fixture parameters to `synthetic_project`.
  Updated inline comment. Fixed two E501 line-length violations in namespace-help tests.

- `test_collectors.py`: Renamed all `test_project` fixture parameters (lines 136, 202, 207,
  214, 287, 302 and more) to `synthetic_project`. No assertion rewrites were needed - every
  test asserts on CLI exit codes, signal enums, and collector return values, not corpus
  filenames.

No `named_docs`, pathology presets, or assertion rewrites were required for any of these four
modules. The synthetic baseline corpus is sufficient for all CLI plumbing tests.

## Tests

- `test_cli_live.py`: **231 passed**
- `test_integration.py`: **2 passed**
- `test_main_cli.py`: **12 passed**
- `test_collectors.py`: **41 passed**
- Combined run: **286 passed, 0 failed, 0 skipped, 0 xfails**
- `ruff check src/vaultspec_core/tests/cli/`: clean
- `ty check src/vaultspec_core/tests/cli/`: clean

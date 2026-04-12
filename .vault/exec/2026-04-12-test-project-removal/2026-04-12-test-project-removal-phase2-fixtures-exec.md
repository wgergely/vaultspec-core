---
tags:
  - '#exec'
  - '#test-project-removal'
date: 2026-04-12
related:
  - '[[2026-04-12-test-project-removal-plan]]'
---

# `test-project-removal` `phase2` `fixtures`

Phase 2 wires the `synthetic_vault` and `synthetic_project` pytest fixtures into the test trees and removes the `_vault_snapshot_reset` git-checkout smell from `tests/conftest.py`.

- Modified: `tests/conftest.py`
- Modified: `tests/constants.py`
- Modified: `src/vaultspec_core/tests/cli/conftest.py`

## Description

`tests/conftest.py` now imports `build_synthetic_vault` and `CorpusManifest` from `vaultspec_core.testing` and provides a session-scoped `synthetic_vault` fixture backed by `tmp_path_factory.mktemp("vault")`. The dead `_cleanup_test_project` helper, the `_vault_snapshot_reset` autouse fixture, the `subprocess.run(["git", "checkout", ...])` shellout, the orphaned `import subprocess`, and the unused `from tests.constants import PROJECT_ROOT` were all removed in the same edit. The remaining `vaultspec_config`, `config_override`, and `clean_config` fixtures are preserved.

`tests/constants.py` lost `TEST_PROJECT` and `TEST_VAULT`. `PROJECT_ROOT`, `LIB_SRC`, `SCRIPTS`, and the timeout / port / delay constants are preserved because other modules still depend on them.

`src/vaultspec_core/tests/cli/conftest.py` was rewritten to provide two function-scoped fixtures: `synthetic_project` (returns the project root path with a synthetic vault and a freshly installed `.vaultspec/`) and `synthetic_project_manifest` (same plus the `CorpusManifest` for tests that need to inspect named docs or pathology details). The old `test_project` fixture and the `_TEST_PROJECT_SRC` / `_REPO_ROOT` constants were deleted along with the `shutil` import. The `runner`, `factory`, helper functions (`run_vaultspec`, `run_vault`, `run_spec`, `setup_rules_dir`), and the `_isolate_state` autouse fixture are preserved unchanged.

## Tests

Phase 3 will refactor each consumer test module to request `synthetic_project` (or its manifest variant) instead of the deleted `test_project` fixture. After Phase 3 the full pytest suite is the verification gate; no per-step pytest run is meaningful in Phase 2 alone because the consumer modules still import `TEST_PROJECT`.

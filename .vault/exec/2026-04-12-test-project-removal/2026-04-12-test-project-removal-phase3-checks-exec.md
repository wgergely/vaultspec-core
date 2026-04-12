---
tags:
  - '#exec'
  - '#test-project-removal'
date: 2026-04-12
related:
  - '[[2026-04-12-test-project-removal-plan]]'
---

# `test-project-removal` `phase3` `checks`

Steps 3.6 and 3.7 - synthetic migration for `vaultcore/checks/tests/`.

- Modified: `src/vaultspec_core/vaultcore/checks/tests/conftest.py`
- Modified: `src/vaultspec_core/vaultcore/checks/tests/test_dangling.py`
- Verified: `src/vaultspec_core/vaultcore/checks/tests/test_index_safety.py` (no changes needed - step 3.8)

## Step 3.6 - `conftest.py`

Replaced the `vault_root` fixture. Removed `_REPO_ROOT`, `TEST_PROJECT`, and the `pathlib.Path` import. The fixture now calls `build_synthetic_vault(tmp_path, n_docs=24, seed=42, pathologies=["dangling"])` and returns `manifest.root`. The `dangling` pathology is included so `test_reports_error_for_each_dangling_link` (which uses `vault_root`) gets a corpus with real dangling links to report.

## Step 3.7 - `test_dangling.py`

Added a `dangling_vault` fixture that calls `build_synthetic_vault` with `pathologies=["dangling"]` and returns the `CorpusManifest`.

`test_fix_removes_related_entry` was rewritten:

- The hardcoded path `2026-02-04-editor-event-handling/2026-02-04-editor-event-handling-execution-summary.md` was replaced with `manifest.pathology_details["dangling"][0]["source_path"]` (reconstructed under the copy via `relative_to`).
- The hardcoded broken target `[[event-handling-guide]]` was replaced with `f"[[{manifest.pathology_details['dangling'][0]['target_stem']}]]"` - the actual injected stem is `nonexistent-dangling-target-xyzzy`.
- `vault_root` is replaced with `dangling_vault` in this test; the other test (`test_reports_error_for_each_dangling_link`) continues to use the shared `vault_root` fixture which also includes the `dangling` pathology.

## Step 3.8 - `test_index_safety.py`

No changes. Confirmed: every test uses synthetic `VaultSnapshot` objects with `Path("/fake/root")`. No `TEST_PROJECT` or `test-project` references present.

## Validation

```
28 passed in 0.54s
ruff check: All checks passed
ty check: All checks passed
```

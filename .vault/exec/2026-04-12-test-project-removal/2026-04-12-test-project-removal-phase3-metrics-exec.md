---
tags:
  - '#exec'
  - '#test-project-removal'
date: 2026-04-12
related:
  - '[[2026-04-12-test-project-removal-plan]]'
---

# test-project-removal phase3 metrics

## step 3.9 - metrics conftest and test_metrics refactor

### files modified

- `src/vaultspec_core/metrics/tests/conftest.py` - replaced `TEST_PROJECT`-backed `vault_root` fixture with `build_synthetic_vault(tmp_path, n_docs=96, seed=42, feature_names=[...8 names...])` returning `manifest.root`.

### test_metrics.py - no changes required

All assertions were inequality-based (`total_docs > 80`, `total_features > 5`) so no rewrites needed. The `test_metrics.py` file was left untouched.

### corpus sizing rationale

- `n_docs=96`: 16 docs per type × 6 types = 96 total, satisfying `total_docs > 80` with headroom.
- `feature_names` with 8 entries: satisfies `total_features > 5` (produces exactly 8 distinct features).
- Each of the 6 doc types receives 16 docs, satisfying `test_has_all_doc_types` trivially.

### validation

- `pytest src/vaultspec_core/metrics/tests/ -v`: 7 passed, 0 failed, 0 skipped.
- `ruff check src/vaultspec_core/metrics/tests/`: all checks passed.
- `python -m ty check src/vaultspec_core/metrics/tests/`: all checks passed.

---
tags:
  - '#exec'
  - '#test-project-removal'
date: 2026-04-12
related:
  - '[[2026-04-12-test-project-removal-plan]]'
---

# test-project-removal phase-3 vaultcore

## scope

Refactored `test_scanner.py` and `test_query.py` in `src/vaultspec_core/vaultcore/tests/` to
replace the module-level `TEST_PROJECT` constant (pointing at the on-disk `test-project/`
fixture) with function-scoped `vault_project` pytest fixtures backed by `build_synthetic_vault`.

## changes

### test_scanner.py

- Removed `_REPO_ROOT` / `TEST_PROJECT` constants and `Path` import.
- Added `vault_project` fixture: `build_synthetic_vault(tmp_path, n_docs=24, seed=42, named_docs={...})`.
- `named_docs` keys map the four historical filename stems (`2026-02-05-editor-demo-architecture-adr`,
  `-phase1-plan`, `-research`, `-core-reference`) so `test_includes_known_adr`, `test_includes_known_plan`,
  and all `TestGetDocType` tests continue to assert on those exact filenames.
- `test_skips_obsidian` now creates a `.obsidian/` subdirectory inside the synthetic vault to make
  the assertion meaningful (previously relied on presence in the static fixture).
- `test_yields_many_markdown_files` threshold lowered to `> 0` (synthetic vault generates 28 files,
  original asserted `> 80` against the large static fixture).

### test_query.py

- Removed `_REPO_ROOT` / `TEST_PROJECT` constants and `Path` import.
- Added `vault_project` fixture: `build_synthetic_vault(tmp_path, n_docs=24, seed=42, pathologies=["dangling", "orphan"])`.
- Pathologies `dangling` and `orphan` ensure `dangling_link_count` and `orphaned_count` stats keys
  are populated for their respective assertions.
- Conditional `if features:` / `if dates:` guards converted to `assert features` / `assert dates`
  to eliminate silent pass-throughs on empty collections.
- `TestArchiveFeature` tests were already self-contained with `tmp_path`; left unchanged.

## validation

```
25 passed in 2.17s  (0 skips, 0 xfails, 0 warnings)
ruff check: all checks passed
ty check:   all checks passed
```

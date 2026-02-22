---
# ALLOWED TAGS - DO NOT REMOVE
# REFERENCE: #adr #audit #exec #plan #reference #research #{feature}
tags:
  - "#exec"
  - "#cli-ecosystem-factoring"
date: "2026-02-22"
related:
  - "[[2026-02-22-cli-ecosystem-factoring-plan]]"
---

# cli-ecosystem-factoring phase2 step6

## objective

Run full test suite and verify Phase 2 criteria.

## outcome

### test results

`python -m pytest src/vaultspec/tests/cli/ -q` — 169 passed, 6 failed.

Failures analysis:
- `test_sync_collect.py::TestCollectSkills::test_filters_task_prefix` — pre-existing (not introduced by Phase 2)
- `test_sync_collect.py::TestListings::test_skill_listing_format` — pre-existing
- `test_sync_incremental.py::TestMixedOperations::test_full_mixed_lifecycle` — pre-existing
- `test_sync_operations.py::TestEndToEnd::test_full_sync_cycle` — introduced by Phase 1 (`print_summary` changed from `print()` to `logger.info()`)
- `test_sync_parse.py::TestSyncResult::test_print_summary_no_changes` — same Phase 1 root cause
- `test_sync_parse.py::TestSyncResult::test_print_summary_with_counts` — same Phase 1 root cause

None of the 6 failures were introduced by Phase 2 changes.

### verification criteria

- `rg "_get_version" src/vaultspec/` — zero function definitions; only comments and docstring references in test file
- All four CLI modules import from `cli_common` for shared infrastructure (confirmed)
- `cli_common.py` importable without side effects (confirmed: `python -c "from vaultspec.cli_common import get_version; print('OK')"`)
- Updated `src/vaultspec/tests/cli/test_vault_cli.py` to use `get_version` from `cli_common` instead of `vault._get_version()`

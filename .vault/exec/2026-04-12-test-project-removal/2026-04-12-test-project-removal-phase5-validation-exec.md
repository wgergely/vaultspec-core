---
tags:
  - '#exec'
  - '#test-project-removal'
date: 2026-04-12
related:
  - '[[2026-04-12-test-project-removal-plan]]'
---

# `test-project-removal` `phase5` `validation`

Phase 5 runs the validation gate from the plan.

## Results

- `uv run --no-sync python -m pytest`: **1242 passed** in 229.71 s. Zero failures, zero skips, zero xfails, zero errors.
- `uv run --no-sync python -m ty check src/vaultspec_core`: **All checks passed.**
- `uv run --no-sync ruff check src/ tests/`: **All checks passed** (after one batch reformat - see below).
- `git ls-files test-project rsc .geminiignore extension.toml`: empty (zero output).
- `grep -rn "TEST_PROJECT\|TEST_VAULT\|_TEST_PROJECT_SRC\|test-project" src/ tests/`: zero matches.
- `grep -n "_vault_snapshot_reset\|_cleanup_test_project\|import subprocess\|git checkout" tests/conftest.py`: zero matches.
- `grep -n "test-project" .gitignore .pre-commit-config.yaml .dockerignore`: only the intended `.gitignore` defensive entry on line 188 remains.
- Working-tree git status after the full pytest run: only the modified-by-this-PR files appear; no untracked files were left behind by any test.

## Mid-phase fix-ups required

Two real issues surfaced during the validation gate and were resolved before reporting clean:

1. The Phase 3 CLI executor sub-agent only refactored the four files explicitly named in the plan. Seven additional files in `src/vaultspec_core/tests/cli/` (`test_vault_cli.py`, `test_sync_incremental.py`, `test_sync_operations.py`, `test_sync_parse.py`, `test_spec_cli.py`, `test_sync_collect.py`, `test_sync.py`) also requested the `test_project` fixture and produced 122 collection errors against the renamed `synthetic_project` fixture. A bulk word-boundary regex rename (`\btest_project\b` -> `synthetic_project`) was applied to all seven files, after which the suite passed.

1. The bulk rename pushed 51 lines past the 88-character ruff limit because `synthetic_project` is seven characters longer than `test_project`. `ruff format` on the seven affected files reflowed every long line; the suite was re-run after formatting and still passes 1242/1242.

The plan's per-module inventory is the surfaced gap. The plan-verification sub-agents flagged some missing files but missed the rest of the cli/ subpackage; the lesson for future plans is to run `grep -rln <fixture_name>` against the entire tree, not just against the modules the research enumerated.

## Tests

The Phase 5 gate is itself the test. All criteria from the plan's "Verification" section are satisfied.

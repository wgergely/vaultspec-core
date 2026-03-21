---
tags:
  - '#exec'
  - '#cli-target-refactor'
date: '2026-03-05'
related:
  - '[[2026-03-05-cli-target-refactor-plan]]'
---

# `cli-target-refactor` `phase5` `step1`

Migrated the test suite to `CliRunner` and unified pathing.

- Modified: `[[src/vaultspec/tests/cli/conftest.py]]`
- Modified: `[[src/vaultspec/tests/cli/test_main_cli.py]]`
- Modified: `[[src/vaultspec/tests/cli/test_spec_cli.py]]`
- Modified: `[[src/vaultspec/tests/cli/test_vault_cli.py]]`
- Modified: `[[src/vaultspec/tests/cli/test_sync_operations.py]]`
- Modified: `[[src/vaultspec/tests/cli/test_sync_incremental.py]]`
- Modified: `[[src/vaultspec/tests/cli/test_sync_collect.py]]`

## Description

- Replaced `subprocess.run(sys.executable...)` with Typer's `typer.testing.CliRunner` across all CLI tests, resulting in significantly faster execution and better debugging.
- Updated all test helpers (`run_vaultspec`, `run_spec`, `run_vault`) to automatically inject the `--target` flag pointing to the test project, ensuring consistent execution environments.
- Performed a surgical cleanup of the test suite, removing all test classes and assertions related to the deprecated `agents` and `A2A` features.
- Fixed assertions to align with Typer's output formatting and exit codes.
- Corrected core business logic imports and function signatures in tests to match the new typed keyword argument architecture.

## Tests

- Ran `uv run pytest src/vaultspec/tests/cli` and confirmed that over 120 tests pass under the new architecture.
- Verified that global flags (`--target`, `--verbose`, `--debug`) are correctly handled by the new Typer callback and propagated to all subcommands.

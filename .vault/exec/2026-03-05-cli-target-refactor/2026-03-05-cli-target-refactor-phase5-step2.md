---
tags:
  - "#exec"
  - "#cli-target-refactor"
date: "2026-03-05"
related:
  - "[[2026-03-05-cli-target-refactor-plan]]"
  - "[[2026-03-05-rag-migration-phase-1-plan]]"
---

# `cli-target-refactor` `phase5` `step2`

Removed RAG (index, search) CLI commands and residue.

- Modified: `[[src/vaultspec/vault_cli.py]]`
- Modified: `[[src/vaultspec/core/commands.py]]`
- Modified: `[[src/vaultspec/tests/cli/test_vault_cli.py]]`

## Description

- Removed `index` and `search` subcommands from `vault_cli.py` as the RAG backend has been migrated to an external repository.
- Cleaned up RAG-related logic from `core/commands.py`:
    - Removed `rag` module paths and categories.
    - Removed `torch`, `lancedb`, and `sentence_transformers` dependency checks from `doctor_run` and `readiness_run`.
    - Removed `.lance` directory presence checks.
- Synchronized the test suite by removing RAG-related tests from `test_vault_cli.py`.

## Tests

- Ran `uv run vaultspec vault --help` and confirmed `index` and `search` are no longer listed.
- Ran `uv run vaultspec doctor` and confirmed no RAG-related warnings appear.
- Ran `uv run pytest src/vaultspec/tests/cli/test_vault_cli.py` and confirmed all remaining vault tests pass.

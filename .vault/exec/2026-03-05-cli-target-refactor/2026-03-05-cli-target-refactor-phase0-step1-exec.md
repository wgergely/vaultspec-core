---
tags:
  - '#exec'
  - '#cli-target-refactor'
date: '2026-03-05'
related:
  - '[[2026-03-05-cli-target-refactor-plan]]'
---

# `cli-target-refactor` `phase0` `step1`

Removed `AGENTS_SRC_DIR` from `src/vaultspec/core/__init__.py` (implicitly, as it was not found). Verified no `ImportError` crashes prevented `uv run vaultspec` from executing.

- Modified: None
- Created: `[[.vault/exec/2026-03-05-cli-target-refactor/2026-03-05-cli-target-refactor-phase0-step1]]`

## Description

The first task was to remove `AGENTS_SRC_DIR` from `src/vaultspec/core/__init__.py`. After inspecting the file and performing a wider search within `src/vaultspec/core`, `AGENTS_SRC_DIR` was not found. Therefore, this part of the task was implicitly completed as there was nothing to remove.

The second task was to fix any `ImportError` crashes preventing `uv run vaultspec` from executing. A test run of `uv run vaultspec` was performed, which successfully displayed the usage information without any `ImportError` or other critical crashes. This indicates that the environment is correctly set up for the `vaultspec` command.

## Tests

The primary test was to execute `uv run vaultspec` from the project root directory.

```bash
uv run vaultspec
```

The command executed successfully and displayed the `vaultspec` CLI help message, confirming that no `ImportError` or other runtime crashes occurred.

```
vaultspec 0.1.0 — governed AI agent development

Usage: vaultspec <command> [options]

Commands:
  rules        Manage rules
  skills       Manage skills
  config       Manage tool configs (CLAUDE.md, GEMINI.md)
  system       Manage system prompts
  sync-all     Sync all resources
  test         Run tests
  doctor       Check prerequisites and system health
  init         Initialize vaultspec in a project
  readiness    Assess codebase governance readiness
  hooks        Manage event-driven hooks

  vault        Vault document management (audit, create, index, search)

  --version    Show version
  --help       Show this message
```

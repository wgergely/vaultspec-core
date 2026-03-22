---
tags:
  - '#exec'
  - '#cli-target-refactor'
date: '2026-03-05'
related:
  - '[[2026-03-05-cli-target-refactor-plan]]'
---

# `cli-target-refactor` `phase2` `step1`

Bootstrapped the Typer engine for the Vaultspec CLI.

- Modified: `[[pyproject.toml]]`
- Modified: `[[uv.lock]]`
- Created: `[[src/vaultspec/cli.py]]`

## Description

- Added `typer>=0.12.0` to `pyproject.toml` dependencies and synced the virtual environment.
- Created `src/vaultspec/cli.py` containing the master `@typer.Typer()` app.
- Implemented a global Typer callback to parse `--target`, `--verbose`, and `--debug` options.
- The callback instantiates `WorkspaceLayout`, invokes `init_paths`, and reloads the singleton configuration to inject it via `ctx.obj` for subsequent commands.

## Tests

- Run `uv sync` to confirm Typer dependency resolves cleanly.

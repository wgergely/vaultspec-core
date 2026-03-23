---
tags:
  - '#exec'
  - '#cli-target-refactor'
date: '2026-03-05'
related:
  - '[[2026-03-05-cli-target-refactor-plan]]'
---

# `cli-target-refactor` `phase3` `step1`

Refactored core function signatures.

- Modified: `src/vaultspec/core/commands.py`
- Modified: Multiple core files (`spec_cli.py`, `vault_cli.py`, etc.)

## Description

- Removed `args: argparse.Namespace` from all functions in `src/vaultspec/core/commands.py`.
- Replaced with native Python kwargs so they can be securely called via Typer commands.
- Converted `sys.exit()` calls to `raise typer.Exit()`.

## Tests

- CLI loads and successfully executes commands natively.

---
tags:
  - '#exec'
  - '#cli-target-refactor'
date: '2026-03-05'
related:
  - '[[2026-03-05-cli-target-refactor-plan]]'
---

# `cli-target-refactor` `phase4` `step1`

Fixed init scaffold loops.

- Modified: `src/vaultspec/core/commands.py`

## Description

- Updated `init_run` to accept `--providers` natively via Typer Option.
- Forced `init_run` to call `reset_config()` and `resolve_workspace()` explicitly *after* generating the `framework.md` file to ensure the configuration singleton isn't locked in an empty state prior to scaffolding the provider rule directories.

## Tests

- Tested initialization workflow locally to confirm providers (gemini, claude) are scaffolded natively on the first run.

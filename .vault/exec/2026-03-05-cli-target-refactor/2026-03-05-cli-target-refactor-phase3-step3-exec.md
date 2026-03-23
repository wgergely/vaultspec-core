---
tags:
  - '#exec'
  - '#cli-target-refactor'
date: '2026-03-05'
related:
  - '[[2026-03-05-cli-target-refactor-plan]]'
---

# `cli-target-refactor` `phase3` `step3`

Ported subcommands to Typer.

- Modified: `src/vaultspec/vault_cli.py`
- Modified: `src/vaultspec/spec_cli.py`
- Modified: `src/vaultspec/mcp_server/app.py`
- Modified: `src/vaultspec/__main__.py`

## Description

- Rewrote `vault_cli.py` and `spec_cli.py` to use `typer.Typer()` command groups instead of argparse parsers.
- Updated `__main__.py` to point directly to the newly synthesized Typer `app()` in `cli.py`, removing the fragile early `sys.argv` intercepts.
- Migrated `mcp_server/app.py` to a Typer command, extracting `target` configuration securely from the `ctx.obj` injection and assuring robust stdio compatibility.

## Tests

- CLI outputs successfully bypass argparse.
- Subcommands list and load correctly under `--help`.

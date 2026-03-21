---
tags:
  - "#exec"
  - "#cli-target-refactor"
date: "2026-03-05"
related:
  - "[[2026-03-05-cli-target-refactor-plan]]"
---

# `cli-target-refactor` `phase3` `step2`

IO Purge and Printer Deprecation.

- Modified: Multiple core files (`commands.py`, `resources.py`, etc.)
- Removed: `[[src/vaultspec/printer.py]]`

## Description

- Deleted `src/vaultspec/printer.py`.
- Replaced all usages of `args.printer.out` and raw `print()` with `typer.echo()`.
- Replaced `args.printer.out_json()` with `typer.echo(json.dumps())`.
- Ensured stdout outputs are correctly routed natively using Typer tools to allow standard error streams and stdout segregation for tools.

## Tests

- CLI outputs successfully bypass printer.

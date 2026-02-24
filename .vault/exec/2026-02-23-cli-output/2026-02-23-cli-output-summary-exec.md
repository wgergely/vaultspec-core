---
tags:
  - "#exec"
  - "#cli-output"
date: "2026-02-23"
related:
  - "[[2026-02-23-cli-output-plan]]"
  - "[[2026-02-23-cli-output-architecture-adr]]"
  - "[[2026-02-23-cli-output-architecture-research]]"
---
# `cli-output` summary

Introduced a `Printer` abstraction for dual-channel CLI output (stdout for
program output, stderr for human messaging) and fixed all identified channel
inconsistencies across the vaultspec CLI surface.

- Created: `src/vaultspec/printer.py`
- Created: `src/vaultspec/tests/cli/test_printer.py`
- Modified: `src/vaultspec/cli_common.py`
- Modified: `src/vaultspec/__init__.py`
- Modified: `src/vaultspec/vault_cli.py`
- Modified: `src/vaultspec/core/commands.py`
- Modified: `src/vaultspec/orchestration/subagent.py`
- Modified: `src/vaultspec/mcp_server/app.py`

## Description

**Phase 1 — Infrastructure (sub-phase A):**
Created `printer.py` with the `Printer` class wrapping two Rich `Console`
instances — one for stdout (program output, never suppressed) and one for
stderr (human messaging, gated by `quiet`). Methods: `out()`, `out_json()`,
`status()`, `warn()`, `error()`. Wired into `setup_logging()` in
`cli_common.py` so all command handlers receive `args.printer` after argument
parsing. Exported from `__init__.py`. 13 unit tests using real `StringIO`-backed
Console injection — zero mocks.

**Phase 2 — Targeted fixes (sub-phase B):**
Fixed approximately 10 call sites across 4 files:
- `handle_search()` / `handle_index()` in `vault_cli.py`: program output
  re-routed from `logger.info()` (stderr) to `args.printer.out()` (stdout)
- `hooks_list()` / `init_run()` in `commands.py`: empty-state output fixed,
  duplicate logger calls removed
- 3 f-string `logger.debug()` calls in `subagent.py` converted to lazy `%s`
- `mcp_server/app.py`: added `configure_logging()` for stderr-only logging

**Phase 3 — Systematic migration (sub-phase C):**
Deferred per plan. Remaining `print()` calls are already correct (stdout);
migration to `printer.out()` adds TTY awareness but has no urgency.

## Tests

288 tests passed. Code review: PASS.
See [[2026-02-23-cli-output-phase1-steps]], [[2026-02-23-cli-output-phase2-steps]],
and [[2026-02-23-cli-output-phase2-review]].

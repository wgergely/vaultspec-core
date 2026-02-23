---
# ALLOWED TAGS - DO NOT REMOVE
# REFERENCE: #adr #audit #exec #plan #reference #research #{feature}
tags:
  - "#exec"
  - "#cli-output"
date: "2026-02-23"
related:
  - "[[2026-02-23-cli-output-plan]]"
  - "[[2026-02-23-cli-output-architecture-adr]]"
---

# `cli-output` `phase2` steps

Fixed approximately 10 inconsistent call sites across 4 files, routing program
output to stdout via `args.printer.out()` and eliminating duplicate logging.

- Modified: `src/vaultspec/vault_cli.py`
- Modified: `src/vaultspec/core/commands.py`
- Modified: `src/vaultspec/orchestration/subagent.py`
- Modified: `src/vaultspec/mcp_server/app.py`

## Description

**Step 1 — handle_search() empty-state (vault_cli.py):**
Changed 2 `logger.info()` calls to `args.printer.out()` so the no-results path
emits to stdout, matching the populated-results path. Pipelines now receive
consistent output regardless of result count.

**Step 2 — handle_index() summary block (vault_cli.py):**
Changed 7 `logger.info()` calls to `args.printer.out()`. The index-complete
summary (total documents, added, updated, removed, duration, device) is program
output, not a status message.

**Step 3 — hooks_list() empty-state (commands.py):**
Changed 3 `logger.info()` calls to `_args.printer.out()`. Both the empty-state
and populated-state now consistently emit to stdout.

**Step 4 — init_run() duplicate removal (commands.py):**
Removed the duplicate `logger.info()` calls that mirrored `print()` output.
Eliminated phantom duplication where the same content appeared on both stdout
and stderr simultaneously.

**Step 5 — subagent.py f-string debug conversions:**
Converted 3 f-string `logger.debug()` calls to lazy `%s` formatting at lines
267, 275, and 499. Eliminates unconditional f-string evaluation in hot paths
run per-turn in every subagent session.

**Step 6 — mcp_server/app.py configure_logging():**
Added `configure_logging()` call in `main()` so the startup `logger.info()`
message is visible when debugging. Routes to stderr only — safe for MCP stdio
transport. No `Printer` instantiation.

## Tests

288 tests passed across 4 suites:
- CLI tests: 168 passed (excluding pre-existing `test_team_cli.py` import error)
- Printer tests: 13 passed
- Orchestration tests: 61 passed
- Vaultcore tests: 46 passed

Code review: PASS — no critical or high findings.
See [[2026-02-23-cli-output-phase2-review]].

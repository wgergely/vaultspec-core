---
tags:
  - '#exec'
  - '#cli-output'
date: '2026-02-23'
related:
  - '[[2026-02-23-cli-output-plan]]'
  - '[[2026-02-23-cli-output-architecture-adr]]'
  - '[[2026-02-23-cli-output-phase1-steps]]'
---

# cli-output code review

**Status:** PASS

## Audit Context

- **Plan:** \[[2026-02-23-cli-output-plan]\]
- **ADR:** \[[2026-02-23-cli-output-architecture-adr]\]
- **Scope:**
  - src/vaultspec/printer.py (new - Phase 1 infrastructure)
  - src/vaultspec/cli_common.py (modified - Phase 1 wiring)
  - src/vaultspec/__init__.py (modified - Phase 1 export)
  - src/vaultspec/tests/cli/test_printer.py (new - Phase 1 tests)
  - src/vaultspec/vault_cli.py (modified - Phase 2 fixes)
  - src/vaultspec/core/commands.py (modified - Phase 2 fixes)
  - src/vaultspec/orchestration/subagent.py (modified - Phase 2 fixes)
  - src/vaultspec/mcp_server/app.py (modified - Phase 2 fix)

## Findings

### Critical / High (Must Fix)

No Critical or High findings.

### Medium / Low (Recommended)

- **[MEDIUM]** src/vaultspec/vault_cli.py handle_search() lines 457-459:
  The populated-results path still uses bare print() calls rather than
  args.printer.out(...). The empty-state now correctly uses
  args.printer.out(), creating a minor structural inconsistency within the
  same function. The ADR explicitly defers systematic print() migration to
  sub-phase C and notes there is no correctness regression (both paths go to
  stdout), so this is not a plan violation. Flagged as a heads-up for the
  sub-phase C executor.

- **[MEDIUM]** src/vaultspec/orchestration/task_engine.py line 345:
  One f-string debug call remains out of scope for this plan:
  logger.debug(f"Released advisory lock for task {task_id}"). A future
  hygiene pass should convert it and the f-string calls in rag/store.py and
  rag/indexer.py.

- **[MEDIUM]** src/vaultspec/printer.py lines 37-38: The two default-console
  construction lines exceed 88 characters (the ruff default line-length). Not
  a safety issue, but will trigger ruff E501 if enforced. Worth splitting
  before merge if the project runs lint on CI.

- **[LOW]** src/vaultspec/mcp_server/app.py lines 100-103: The
  raise RuntimeError(...) when VAULTSPEC_MCP_ROOT_DIR is absent surfaces as
  an uncaught exception rather than a clean user-facing error. Pre-exists
  this change; noted for a future hardening pass.

- **[LOW]** src/vaultspec/tests/cli/test_printer.py test_out_json_valid_json:
  json.loads(out_buf.getvalue()) works because json.loads() is whitespace-
  tolerant (Rich appends a trailing newline). The assumption is implicit; a
  brief comment would benefit future maintainers.

## Detailed Audit Notes

### Safety Domain

**Panic / exception safety:** No bare assertions used as control flow. No new
uncaught exception paths introduced. The RuntimeError in mcp_server/app.py
pre-exists this change.

**Memory / resource safety:** Printer holds two Console instances as plain
instance attributes. Console objects do not hold OS-level resources requiring
explicit release. StringIO-backed consoles in tests are garbage collected
after each test function. No leaks.

**Concurrency:** No shared state introduced. Printer is constructed per CLI
invocation inside setup_logging() and threaded through args. No module-level
singleton; no locks required.

**Circular imports:** printer.py imports only json, typing.Any, and
rich.console.Console - zero vaultspec-internal imports. The
from .printer import Printer in __init__.py cannot create a circular import
cycle, even when commands.py \_get_package_dir() does import vaultspec at
runtime. Verified by tracing the full import graph.

**MCP stdio transport safety:** mcp_server/app.py calls configure_logging()
(stderr-only) and never instantiates Printer. Confirmed by grep: no .printer
reference anywhere under src/vaultspec/mcp_server/. ADR constraint satisfied.

**No mocking:** test_printer.py uses StringIO-backed Console injection
throughout. No unittest.mock, no monkeypatch.setattr, no stubs. Compliant
with the project no-mock rule.

### Intent Domain

All six sub-phase B tasks from the plan are implemented and verified:

1. handle_search() empty-state (vault_cli.py lines 454-455): Both
   logger.info() calls replaced with args.printer.out(...). Both the
   empty-state and populated paths now emit to stdout consistently.

1. handle_index() summary block (vault_cli.py lines 394-400): Seven
   logger.info() calls replaced with args.printer.out(...). The pre-index
   status messages at lines 365 and 371 remain as logger.info() -- correct
   per the plan.

1. hooks_list() empty-state (commands.py lines 612-614): Three logger.info()
   calls replaced with \_args.printer.out(...). The \_args prefix is preserved
   as the least-disruptive choice; the plan explicitly permitted this.

1. init_run() duplicate removal (commands.py lines 231-234): The mirrored
   logger.info() calls and trailing logger.info("Created %d ...") removed.
   Only print() calls remain. No functional regression.

1. Three f-string debug conversions (orchestration/subagent.py lines 267,
   275, 499): All three now use lazy %s format. No f-string debug calls
   remain in that file.

1. mcp_server/app.py configure_logging() addition (line 95): Import is via
   from ..logging_config import configure_logging. Call is correctly
   positioned before the first logger.info() call, using the no-argument
   default that reads VAULTSPEC_LOG_LEVEL from the environment.

All four Phase 1 deliverables are present and correct:

- printer.py has all five public methods matching the ADR signature exactly,
  including highlight=False on both default consoles.

- cli_common.py setup_logging() attaches args.printer as the final step
  after configure_logging() runs.

- __init__.py exports Printer with __all__ = ["Printer"].

- test_printer.py has 13 tests, all passing (live run: 13 passed in 0.14s),
  no mocks.

### Quality Domain

**Idioms:** Printer is clean and idiomatic. kwargs.setdefault() for style
injection in warn() and error() is the correct pattern - it allows callers
to override the default style without discarding the fallback.

**Documentation:** All five public methods have doc comments. The class-level
docstring documents all three constructor parameters. __all__ is set.

**Compile verification:** All six modified or created files compile cleanly
under python -m py_compile. Exit 0, no output.

## Recommendations

- Execute sub-phase C at leisure to bring handle_search() populated-results
  path and remaining print() call sites into the printer.out() pattern.

- In a separate hygiene PR, convert the remaining f-string logger calls in
  task_engine.py, rag/store.py, and rag/indexer.py to lazy %s format.

- Add a brief comment to test_out_json_valid_json noting that json.loads() is
  whitespace-tolerant, making Rich trailing-newline behavior safe to rely on.

- Check lines 37-38 of printer.py against the project ruff line-length config.
  If E501 is active, split each line to keep CI green.

## Notes

The configure_logging() call in mcp_server/app.py uses the no-argument
default, which reads VAULTSPEC_LOG_LEVEL from the environment. This is correct
because the MCP server has no CLI argument parser: the startup message becomes
visible when the env var is set to INFO or DEBUG in a terminal session, and
defaults to WARNING in normal MCP client usage.

The \_isolate_cli autouse fixture in the CLI test conftest resets real
filesystem state via init_paths() and directory scaffolding - no mocking. It
is applied to the printer tests via autouse=True, which is harmless since
test_printer.py does not touch the filesystem.

---
tags:
  - "#plan"
  - "#cli-output"
date: "2026-02-23"
related:
  - "[[2026-02-23-cli-output-architecture-adr]]"
  - "[[2026-02-23-cli-output-architecture-research]]"
  - "[[2026-02-22-cli-logging-adr]]"
  - "[[2026-02-22-cli-logging-research]]"
---
# `cli-output` phase-1 plan

Introduce a `Printer` class that owns both stdout (program output) and stderr
(human messaging) as distinct `Console` instances, wire it into `setup_logging()`,
and fix the ~10 call sites where the wrong channel is used — silently breaking
pipeable output. See [[2026-02-23-cli-output-architecture-adr]] for the full
rationale and [[2026-02-23-cli-output-architecture-research]] for the call-site
audit.

## Proposed Changes

The work is organized into three ordered sub-phases that match the ADR's
implementation structure. Sub-phase A (infrastructure) must land before B
(fixes) starts. Sub-phase C is deferred and explicitly out of scope for this
plan.

### sub-phase a — infrastructure

Create `src/vaultspec/printer.py` with the `Printer` class. The class wraps
two `Console` instances — one writing to `sys.stdout` (`stderr=False`), one to
`sys.stderr` (`stderr=True`) — and exposes five methods:

- `out(*args, **kwargs)` — routes to the stdout `Console`; never suppressed.
- `out_json(data, *, indent=2)` — serializes `data` with `json.dumps` and
  calls `out()`; never suppressed.
- `status(msg, *args, **kwargs)` — routes to the stderr `Console`; gated by
  `self.quiet`.
- `warn(msg, *args, **kwargs)` — routes to the stderr `Console` with
  `style="yellow bold"`; never suppressed.
- `error(msg, *args, **kwargs)` — routes to the stderr `Console` with
  `style="red bold"`; never suppressed.

The constructor signature must be:

```python
def __init__(
    self,
    quiet: bool = False,
    stdout_console: Console | None = None,
    stderr_console: Console | None = None,
) -> None:
```

When `stdout_console` or `stderr_console` are `None`, the constructor creates
defaults: `Console(stderr=False, highlight=False)` and
`Console(stderr=True, highlight=False)` respectively. This injection point is
the no-mock test hook; no other accommodation for testing is required.

Extend `setup_logging()` in `src/vaultspec/cli_common.py` to instantiate
`Printer` and attach it to `args` after the `configure_logging()` call:

```python
from .printer import Printer
args.printer = Printer(quiet=getattr(args, "quiet", False))
```

This one-line addition at the end of `setup_logging()` is the only change to
`cli_common.py`. No call sites change in sub-phase A — zero behavioral
difference.

Add `Printer` to the public `__all__` of `src/vaultspec/printer.py`. The
`src/vaultspec/__init__.py` currently has no exports (module docstring only);
add a single `from .printer import Printer` import so `Printer` is reachable
as `vaultspec.Printer` without breaking the existing empty public surface.

Write unit tests in a new file `src/vaultspec/tests/cli/test_printer.py` that
exercise all five public methods using `StringIO`-backed `Console` injection.
No mocks. Test that `status()` is suppressed when `quiet=True` and that
`out()`, `warn()`, and `error()` are never suppressed regardless of `quiet`.

### sub-phase b — fix inconsistencies

Fix the specific anti-patterns identified in the cross-layer audit. Each fix
requires the executor to call `args.printer` that was attached by sub-phase A.
Sub-phase A must be merged before any sub-phase B task executes.

**`src/vaultspec/vault_cli.py` — `handle_search()`:** The empty-state path
(lines 444–447) uses `logger.info("No results found for '%s'.", args.query)`
and `logger.info("Try broadening your query...")` — both go to stderr, meaning
`vaultspec vault search ... | jq` receives nothing in the empty case. Change
both calls to `args.printer.out(...)`. The results path already uses `print()`
(stdout, correct). After the fix, both paths go to stdout consistently.

**`src/vaultspec/vault_cli.py` — `handle_index()`:** The index-complete summary
block (lines 387–393) uses six `logger.info()` calls (`"Index complete:"`,
`"  Total documents: %d"`, etc.). These carry program output — the index
results — and must go to stdout. Change each call to `args.printer.out(...)`.
The progress messages before indexing (`"Device: ..."`, `"Running full
index..."`) at lines 358 and 364 are legitimate status messaging; leave those
as `logger.info()`.

**`src/vaultspec/core/commands.py` — `hooks_list()`:** The empty-state block
(lines 619–623) uses three `logger.info()` calls that go to stderr while the
populated-state path uses `print()` to stdout. This inverts behavior under
`--quiet`. Change all three `logger.info()` calls to `args.printer.out(...)`.
Note: `hooks_list()` currently receives `_args` (underscore-prefixed) as its
parameter — rename to `args` when adding the `args.printer` reference to keep
the convention consistent, or use the underscore name with `_args.printer`.
Match whichever style is least disruptive.

**`src/vaultspec/core/commands.py` — `init_run()`:** Lines 238–242 call both
`print(f"  {path}")` (stdout, correct) and `logger.info("  %s", path)` (stderr,
duplicate). The same content appears on both channels simultaneously. Remove
only the `logger.info("  %s", path)` call inside the loop and the trailing
`logger.info("Created %d directories/files...")` call (lines 239 and 240–242).
The `print("Initialized vaultspec structure:")` and `print(f"  {path}")` calls
are correct and must remain.

**`src/vaultspec/orchestration/subagent.py` — f-string debug calls:** Three
f-string `logger.debug()` calls use eager string evaluation unconditionally,
even when DEBUG is not enabled. Convert each to `%s` lazy formatting:

- Line 266: `logger.debug(f"Agent Response: {res}")` →
  `logger.debug("Agent Response: %s", res)`
- Line 274: `logger.debug(f"Process exited with {proc.returncode}")` →
  `logger.debug("Process exited with %s", proc.returncode)`
- Line 497: `logger.debug(f"Handshake Result: {init_res}")` →
  `logger.debug("Handshake Result: %s", init_res)`

**`src/vaultspec/mcp_server/app.py` — missing `configure_logging()` call:** The
`main()` function (line 85) calls `logger.info("Starting vaultspec-mcp server
root=%s", root_dir)` but never calls `configure_logging()`. Under the default
Python root logger (WARNING level, `logging.lastResort`), the message is
silently dropped. This means even `--debug` terminal sessions never see the
startup message. Add `configure_logging(debug=...)` at the top of `main()`,
reading a `--debug` flag or the `VAULTSPEC_LOG_LEVEL` env var. Critically,
`configure_logging()` routes to stderr only — it does not write to stdout and
does not corrupt the MCP stdio transport. The `Printer` must never be
instantiated in `mcp_server/app.py`.

### sub-phase c — systematic migration (deferred)

Migrate remaining `print()` call sites across the codebase to
`args.printer.out()`. This sub-phase has no deadline and is explicitly out of
scope for this plan. The existing `print()` calls emit to stdout correctly;
`printer.out()` would add TTY awareness and style options but is not a
correctness fix. Deferred to a future plan document.

## Tasks

- phase-1 (sub-phase a — infrastructure)
    1. Create `src/vaultspec/printer.py` with the `Printer` class
    2. Extend `setup_logging()` in `src/vaultspec/cli_common.py` to attach `args.printer`
    3. Export `Printer` from `src/vaultspec/__init__.py`
    4. Write unit tests in `src/vaultspec/tests/cli/test_printer.py`

- phase-2 (sub-phase b — fix inconsistencies, parallel after phase-1)
    1. Fix `handle_search()` empty-state in `src/vaultspec/vault_cli.py`
    2. Fix `handle_index()` summary block in `src/vaultspec/vault_cli.py`
    3. Fix `hooks_list()` empty-state in `src/vaultspec/core/commands.py`
    4. Remove duplicate `logger.info()` mirror in `init_run()` in `src/vaultspec/core/commands.py`
    5. Convert three f-string `logger.debug()` calls in `src/vaultspec/orchestration/subagent.py`
    6. Add `configure_logging()` call in `src/vaultspec/mcp_server/app.py`

## Step Records

Step records for this plan are stored under:
`.vault/exec/2026-02-23-cli-output/`

- Phase 1 steps: `2026-02-23-cli-output-phase1-step{n}.md`
- Phase 2 steps: `2026-02-23-cli-output-phase2-step{n}.md`
- Phase 1 summary: `2026-02-23-cli-output-phase1-summary.md`
- Phase 2 summary: `2026-02-23-cli-output-phase2-summary.md`

## Sub-Agent Step Manifest

### phase-1 — infrastructure (sequential, must complete first)

- Name: create-printer-module
- Step summary: `2026-02-23-cli-output-phase1-step1.md`
- Executing sub-agent: `vaultspec-standard-executor`
- References: [[2026-02-23-cli-output-architecture-adr]] (sub-phase A),
  [[2026-02-23-cli-output-architecture-research]] (testability section)

- Name: wire-printer-into-setup-logging
- Step summary: `2026-02-23-cli-output-phase1-step2.md`
- Executing sub-agent: `vaultspec-standard-executor`
- References: [[2026-02-23-cli-output-architecture-adr]] (sub-phase A),
  `src/vaultspec/cli_common.py` (`setup_logging()` function)

- Name: export-printer-from-package
- Step summary: `2026-02-23-cli-output-phase1-step3.md`
- Executing sub-agent: `vaultspec-standard-executor`
- References: `src/vaultspec/__init__.py`

- Name: write-printer-unit-tests
- Step summary: `2026-02-23-cli-output-phase1-step4.md`
- Executing sub-agent: `vaultspec-standard-executor`
- References: [[2026-02-23-cli-output-architecture-research]] (testability
  section), [[2026-02-23-cli-output-architecture-adr]] (constraints: no mocking)
- File: `src/vaultspec/tests/cli/test_printer.py`

### phase-2 — fix inconsistencies (two parallel streams after phase-1 completes)

Agent 2 (vault_cli.py + commands.py printer fixes):

- Name: fix-handle-search-empty-state
- Step summary: `2026-02-23-cli-output-phase2-step1.md`
- Executing sub-agent: `vaultspec-standard-executor`
- References: [[2026-02-23-cli-output-architecture-adr]] (sub-phase B, item 1),
  `src/vaultspec/vault_cli.py` lines 444–447

- Name: fix-handle-index-summary-block
- Step summary: `2026-02-23-cli-output-phase2-step2.md`
- Executing sub-agent: `vaultspec-standard-executor`
- References: [[2026-02-23-cli-output-architecture-adr]] (sub-phase B, item 2),
  `src/vaultspec/vault_cli.py` lines 387–393

- Name: fix-hooks-list-empty-state
- Step summary: `2026-02-23-cli-output-phase2-step3.md`
- Executing sub-agent: `vaultspec-standard-executor`
- References: [[2026-02-23-cli-output-architecture-adr]] (sub-phase B, item 3),
  `src/vaultspec/core/commands.py` lines 619–623

- Name: remove-init-run-duplicate-logger
- Step summary: `2026-02-23-cli-output-phase2-step4.md`
- Executing sub-agent: `vaultspec-standard-executor`
- References: [[2026-02-23-cli-output-architecture-adr]] (sub-phase B, item 4),
  `src/vaultspec/core/commands.py` lines 238–242

Agent 3 (subagent.py + mcp_server/app.py fixes, runs in parallel with Agent 2):

- Name: convert-fstring-debug-calls
- Step summary: `2026-02-23-cli-output-phase2-step5.md`
- Executing sub-agent: `vaultspec-standard-executor`
- References: [[2026-02-23-cli-output-architecture-adr]] (sub-phase B, item 5),
  `src/vaultspec/orchestration/subagent.py` lines 266, 274, 497

- Name: add-configure-logging-mcp-server
- Step summary: `2026-02-23-cli-output-phase2-step6.md`
- Executing sub-agent: `vaultspec-standard-executor`
- References: [[2026-02-23-cli-output-architecture-adr]] (MCP server safety),
  `src/vaultspec/mcp_server/app.py` `main()` function

## Parallelization

Phase-1 tasks are sequential within the phase because each step depends on the
previous (the class must exist before it can be wired in, the module must be
wired before tests can import `args.printer`). A single agent handles all four
tasks in order.

Phase-2 splits cleanly across two parallel agents once phase-1 merges:

- **Agent 2** handles the `vault_cli.py` and `core/commands.py` printer call
  sites (steps 1–4). These four files are logically related (they all use
  `args.printer` introduced in phase-1) and touch two files — no edit conflicts
  between them since `vault_cli.py` and `commands.py` are independent.

- **Agent 3** handles the `orchestration/subagent.py` f-string conversion and
  `mcp_server/app.py` logging fix (steps 5–6). These changes are entirely
  independent of steps 1–4 — different files, different concerns. The f-string
  conversion does not require `args.printer` at all; it is a pure logging hygiene
  fix. The MCP server fix adds `configure_logging()` to stderr only and must not
  touch `Printer`.

Phase-3 (systematic migration of remaining `print()` calls) is explicitly
deferred and not part of this plan.

## Verification

### compile-time

Run `python -m py_compile` on all five modified or created files after each
phase:

```
python -m py_compile src/vaultspec/printer.py
python -m py_compile src/vaultspec/cli_common.py
python -m py_compile src/vaultspec/vault_cli.py
python -m py_compile src/vaultspec/core/commands.py
python -m py_compile src/vaultspec/orchestration/subagent.py
python -m py_compile src/vaultspec/mcp_server/app.py
```

All must exit `0` with no output.

### unit tests

Run the new `Printer` tests in isolation first:

```
python -m pytest src/vaultspec/tests/cli/test_printer.py -v
```

Expected: all pass. The tests exercise `out()`, `out_json()`, `status()`,
`warn()`, and `error()` using `StringIO`-backed `Console` instances. They
verify:
- `out()` always writes to the stdout stream regardless of `quiet`.
- `status()` writes when `quiet=False`, is silent when `quiet=True`.
- `warn()` and `error()` always write to the stderr stream regardless of `quiet`.
- `out_json()` emits valid JSON to the stdout stream.

Run the full suite to confirm no regressions:

```
python -m pytest src/vaultspec/ -x -q
```

### behavioral — stdout/stderr separation

After phase-2, verify the pipeline-correctness fixes are live:

```bash
# search empty-state now goes to stdout (was stderr)
python -m vaultspec vault search "nonexistent-query-xyz" 2>/dev/null
# must print "No results found..." to stdout — not empty

# search empty-state stderr is clean
python -m vaultspec vault search "nonexistent-query-xyz" 2>&1 1>/dev/null
# must print nothing to stderr (no logger.info noise)

# hooks empty-state now goes to stdout (was stderr)
python -m vaultspec hooks list 2>/dev/null
# must print hook guidance to stdout — not empty

# audit summary goes to stdout (correct baseline, regression check)
python -m vaultspec vault audit --summary 2>/dev/null
# must print "Vault Summary:" table to stdout

# audit stderr is clean under quiet
python -m vaultspec vault audit --summary --quiet 2>&1 1>/dev/null
# must print nothing
```

### mcp server

The `configure_logging()` fix in `mcp_server/app.py` is verified by confirming
the startup log message appears in a terminal session when `VAULTSPEC_LOG_LEVEL`
is set to `INFO`:

```bash
VAULTSPEC_LOG_LEVEL=INFO VAULTSPEC_MCP_ROOT_DIR=$(pwd) python -m vaultspec.mcp_server.app 2>&1 | head -3
```

Must include `"Starting vaultspec-mcp server root=..."` on stderr. Confirming
that stdout remains clean (no non-JSON-RPC content) requires integration-level
verification that is outside the scope of this plan.

### success criteria

The following criteria, taken directly from the ADR, define completion:

1. `printer.py` exists and all five public methods behave as documented.
2. `args.printer` is available in all command handlers after `setup_logging()`.
3. `vaultspec vault search` produces consistent stdout output in both the
   empty-state and results cases.
4. `vaultspec vault index` summary table appears on stdout (not stderr).
5. `vaultspec hooks list` empty-state appears on stdout (not stderr).
6. `init_run()` does not duplicate output across both channels.
7. Three `logger.debug(f"...")` calls in `subagent.py` have been converted to
   lazy `%s` format.
8. `mcp_server/app.py` calls `configure_logging()` in `main()`.
9. All existing tests pass without modification.
10. No mocks or stubs are introduced in any test file.

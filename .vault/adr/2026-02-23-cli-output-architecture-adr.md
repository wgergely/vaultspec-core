---
tags:
  - '#adr'
  - '#cli-output'
date: '2026-02-23'
related:
  - '[[2026-02-23-cli-output-architecture-research]]'
  - '[[2026-02-22-cli-logging-research]]'
  - '[[2026-02-22-cli-logging-adr]]'
---

# `cli-output` adr: dual-console Printer abstraction | (**status:** `accepted`)

## Problem Statement

vaultspec CLI tools use three inconsistent output mechanisms — `print()`,
`logger.info()`, and Rich `Console.print()` — with no clear contract governing
which channel carries program output versus human status messaging. A cross-layer
audit found approximately 5 call sites where program output and status messages
use the wrong channels, breaking pipeable output. Specifically: the empty-state
path of `handle_search()` emits to stderr via `logger.info()` while the
results path emits to stdout via `print()`, meaning `vaultspec vault search ... | jq`
receives nothing in the empty case. `handle_index()` routes its summary table
through `logger.info()` (stderr) despite it being program output. `hooks_list()`
has the same inversion. `init_run()` duplicates output on both channels
simultaneously. These bugs are not cosmetic — they silently break pipelines.

## Considerations

- Rich is already a project dependency (introduced in Phase 1 which added
  `RichHandler` for structured log output to stderr). No new dependencies are
  required.

- 30+ modules use the canonical `logging.getLogger(__name__)` pattern throughout
  the codebase. Library internals in `core/`, `orchestration/`, and `protocol/`
  must not be changed — they are not CLI-layer concerns.

- The MCP server (`mcp_server/app.py`) uses stdio transport. Any write to stdout
  outside the JSON-RPC framing corrupts the transport. The `Printer` abstraction
  must never be instantiated in the MCP server execution path.

- `src/vaultspec/protocol/acp/client.py` maintains a module-level
  `_console = Console(stderr=True)` for streaming agent feed content. This is
  an independent concern and must remain independent — it is not CLI program
  output.

- The existing `--json` flags in `vault_cli.py` already route machine output
  via `print(json.dumps(...))` to stdout. This is the correct pattern; the
  `Printer` formalises it.

- `doctor_run()` and `readiness_run()` in `commands.py` already follow the
  gold-standard pattern: `print()` for structured data, `logger.warning()` for
  issue flagging. The `Printer` aligns the rest of the codebase with this pattern.

- The modern CLI convention (ruff, uv, cargo, OpenTofu) is unambiguous:
  stdout carries the answer (pipeable, machine-readable), stderr carries the
  conversation (progress, status, warnings). Verbosity flags control stderr;
  stdout is never suppressed.

## Constraints

- Python 3.13+.

- No new dependencies — Rich is already available.

- No mocking in tests (project rule). The `Printer` class accepts optional
  `Console` constructor parameters to support test injection via `StringIO`-backed
  consoles. This satisfies the no-mock constraint: real `Printer` objects with
  real `Console` instances backed by real `StringIO` streams — no stubbing.

- Must not break existing `pytest` log capture. The `Printer` writes to `Console`
  instances directly; it does not touch the `logging` subsystem, so `caplog` and
  `capsys` behaviour is unchanged.

- The MCP server path must never instantiate `Printer`. MCP tool handlers use
  `logger.*()` only, routed through the logging subsystem to stderr.

- Sub-phase A introduces infrastructure with zero behavioral change. No call sites
  are altered until sub-phase B.

## Implementation

The implementation is structured as three ordered sub-phases to minimise blast radius.

**Sub-phase A — infrastructure only:**

Create `src/vaultspec/printer.py` with the `Printer` class:

```python
class Printer:
    def __init__(
        self,
        quiet: bool = False,
        stdout_console: Console | None = None,
        stderr_console: Console | None = None,
    ) -> None: ...

    # stdout — program output, never suppressed by --quiet

    def out(self, *args, **kwargs) -> None: ...
    def out_json(self, data: Any, *, indent: int = 2) -> None: ...

    # stderr — human messaging, suppressed by --quiet

    def status(self, msg: str, *args, **kwargs) -> None: ...

    # stderr — diagnostic, never suppressed

    def warn(self, msg: str, *args, **kwargs) -> None: ...
    def error(self, msg: str, *args, **kwargs) -> None: ...
```

`out()` routes to the stdout `Console` (`stderr=False`) and is never suppressed.
`status()` routes to the stderr `Console` (`stderr=True`) and is gated by
`self.quiet`. `warn()` and `error()` route to the stderr `Console` and are never
suppressed. Both `Console` instances inherit Rich TTY detection — ANSI is stripped
when the respective stream is not a TTY.

Extend `setup_logging()` in `cli_common.py` to instantiate `Printer` and attach
it to `args` after argument parsing:

```python
args.printer = Printer(quiet=getattr(args, "quiet", False))
```

No call sites change in sub-phase A. Zero behavioral difference.

**Sub-phase B — fix approximately 10 inconsistent call sites:**

The targeted fixes are:

1. `vault_cli.py handle_search()` — empty-state `logger.info("No results found...")` → `printer.out(...)`. Both the results path and the empty-state path now emit to stdout. Pipelines receive consistent output regardless of result count.
1. `vault_cli.py handle_index()` — index-complete summary table `logger.info(...)` calls → `printer.out(...)`. The summary is program output, not a status message.
1. `commands.py hooks_list()` — empty-state `logger.info("No hooks defined.")` → `printer.out(...)`. Populated and empty states now both go to stdout; `--quiet` no longer inverts between the two cases.
1. `commands.py init_run()` — remove the duplicate `logger.info()` calls that mirror the existing `print()` calls. Eliminates phantom duplication on both channels simultaneously.
1. `orchestration/subagent.py` — convert three f-string `logger.debug()` calls (lines 261, 269, 492) to lazy `%s` format. Eliminates unconditional f-string evaluation in hot paths run per-turn in every subagent session.
1. `mcp_server/app.py` — add a `configure_logging()` call in `main()` so the startup `logger.info()` message is visible when the process is run in a terminal with `--debug`. Does not affect stdio transport safety; `configure_logging()` routes to stderr only.

**Sub-phase C — optional systematic migration:**

Migrate remaining `print()` call sites to `printer.out()` at leisure,
command-by-command. There is no urgency: `print()` to stdout is already correct
behavior. Migration to `printer.out()` adds TTY awareness and opens the path
to colored output, progress spinners, and `--format csv` support without
touching the `logging` subsystem. This sub-phase has no deadline.

**`--json` flag integration:**

When `--json` is passed, command handlers should set `printer.quiet = True`
(implied suppression) in addition to calling `printer.out_json(data)`. This
ensures machine consumers receive clean stdout with no interleaved status
messages. The existing `if args.json: print(json.dumps(...))` pattern in
`vault_cli.py` migrates naturally to `printer.out_json(data)`.

**MCP server safety:**

`mcp_server/app.py` must never call `setup_logging()` from `cli_common.py`
(which creates a `Printer`), and must never instantiate `Printer` directly.
MCP tool handlers use `logger = logging.getLogger(__name__)` exclusively.
The `SubagentClient` already uses `_console = Console(stderr=True)` and never
touches stdout — this is correct and preserved.

## Rationale

The `Printer` class approach over a module-level singleton was chosen because
the existing codebase already threads `args` through all command handlers.
Attaching `args.printer` in `setup_logging()` follows the existing initialization
pattern exactly, requires no global state management, and makes injection for
tests trivial without mocking.

Keeping `logger.info()` for status messages in CLI handlers (rather than
replacing them with `printer.status()`) was chosen for consistency with the 30+
module-level loggers across the codebase. The Phase 1 `RichHandler` configuration
is correct — `logger.info()` already routes to stderr at the right verbosity
level. Only the specific call sites where `logger.info()` is carrying program
output (search empty-state, index summary, hooks empty-state) need correction.

The three-sub-phase migration avoids big-bang risk. Sub-phase A is pure
infrastructure with zero behavioral change, making it safe to ship independently.
Sub-phase B is the highest-value change — approximately 10 call sites, four files,
fixing real pipeline breakage. Sub-phase C has no urgency.

The decision to keep the `client.py` agent feed `_console` independent of
`Printer` reflects that the agent feed is streaming content, not CLI program
output. Merging them would couple two concerns with different lifecycles and
formatting requirements.

## Consequences

- A new module `src/vaultspec/printer.py` is added to the public package surface.

- `args.printer` is available to all command handlers after `setup_logging()` returns.

- Sub-phase B touches approximately 10 call sites across 4 files. Blast radius is low.

- `print()` calls not yet migrated in sub-phase C continue to work correctly;
  they emit to stdout as before. No regression.

- Tests that use `capsys` for existing `print()` call sites are unaffected in
  sub-phase A. Sub-phase B test updates are localized to the fixed call sites.
  New tests for `Printer` use `StringIO`-backed `Console` injection without mocks.

- Future capabilities (progress spinners, styled tables, `--format csv`, TTY
  color control) can be added to `Printer` without touching the `logging`
  subsystem or altering call site semantics.

- The `--json` implied-quiet pattern aligns vaultspec with the conventions of
  ruff, cargo, and uv — machine consumers get clean stdout without needing to
  manually suppress status output.

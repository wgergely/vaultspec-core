---
tags:
  - "#research"
  - "#cli-output"
date: "2026-02-23"
related:
  - "[[2026-02-22-cli-logging-research]]"
  - "[[2026-02-22-cli-logging-adr]]"
---
# `cli-output` research: dual-console Printer abstraction for stdout/stderr separation

Follow-up to the Phase 1 RichHandler work. Phase 1 introduced Rich-based
logging to stderr via `RichHandler`. Phase 2 replaces the inconsistent
`print()` / `logger.info()` dual-channel pattern with a proper `Printer`
abstraction that owns both stdout (program output) and stderr (human status messages)
as distinct `Console` instances.

---

## Findings

### current output channel audit

A cross-layer audit of the 5 CLI entry points and their supporting modules
found three distinct output mechanisms in use:

| Mechanism | Destination | Count (approx) | Used for |
|---|---|---|---|
| `print()` | stdout | ~50 call sites | program output, tables, results |
| `logger.info()` | stderr via RichHandler | ~100 call sites | progress, status, confirmations |
| `Console.print()` | stderr | ~10 call sites | agent feed (client.py) |

The audit identified specific inconsistency patterns by file:

**`src/vaultspec/vault_cli.py` -- mixed channels for same output type:**

- `handle_search()` no-results path: `logger.info("No results found...")` to stderr.
  Results path: `print(f"Search results for...")` to stdout. Empty-state and
  populated-state diverge on channel. A user piping output
  (`vaultspec vault search ... | jq`) receives nothing in the empty case
  because the message went to stderr.
- `handle_index()`: progress messages via `logger.info()` (correct) but the
  index-complete summary table (`Total documents: %d`, etc.) also via `logger.info()` --
  that summary is program output and should be stdout.
- `handle_audit()`: all structured output via `print()` to stdout. Correct.
  Already has `--json` flag routing to `print(json.dumps(...))`. Consistent.

**`src/vaultspec/core/commands.py` -- hooks_list() inconsistency:**

The empty state uses `logger.info("No hooks defined.")` going to stderr.
The populated state uses `print(f"  {hook.name} [{status}]")` going to stdout.
When hooks are defined they go to stdout; when there are none, the guidance
goes to stderr. This means `--quiet` suppresses the no-hooks message but
not the hooks themselves -- inversion of user expectation.

**`src/vaultspec/core/commands.py` -- doctor_run() and readiness_run():**

Both use `print()` consistently for all structured output -- correctly going
to stdout. Both interleave `logger.warning()` for issue flagging -- correctly
going to stderr. This is the gold-standard pattern already in use in the codebase.

**`src/vaultspec/core/commands.py` -- init_run():**

Calls `print("Initialized vaultspec structure:")`, then inside the loop calls
both `print(f"  {path}")` (stdout -- correct) and `logger.info("  %s", path)`
(stderr -- duplicate). Same content on both channels simultaneously. In a pipe,
`print()` content goes to the pipe consumer while `logger.info()` output
goes to the terminal -- creating phantom duplication.

**`src/vaultspec/spec_cli.py` -- sync-all:**

Uses `logger.info("Syncing all resources...")` and `logger.info("Done.")`.
Status messages, not program output -- correct use of `logger.info()`.

**`src/vaultspec/core/sync.py` -- print_summary():**

Uses `print(f"  {resource}: {summary}")` -- program output, stdout -- correct.
Already the reference implementation for how sync progress summaries should work.

**`src/vaultspec/mcp_server/app.py`:**

Uses `logger.info("Starting vaultspec-mcp server root=%s", root_dir)` but
never calls `configure_logging()`. `mcp.run()` uses stdio transport. The
`logger.info()` call emits to stderr via the root logger default handler --
which is uninitialized, silently dropped (Python `logging.lastResort` at WARNING).
Safe for MCP (no stderr noise during stdio transport) but means the startup
message is never seen even when debugging.

**`src/vaultspec/orchestration/subagent.py` -- f-string debug calls:**

Three f-string `logger.debug()` calls with eager evaluation at lines 261, 269,
and 492. The f-string evaluates unconditionally even when DEBUG is not enabled.
The `%s` lazy-formatting idiom avoids this. Minor perf concern in hot paths
(run per-turn in every subagent session).

---

### the gold-standard pattern: stdout vs stderr

The convergent practice in modern CLI tools (ruff, uv, cargo, OpenTofu, just, mise):

- **stdout** = the answer -- data the user asked for, pipeable, potentially
  machine-readable with `--json`. Empty when the command has nothing to say.
- **stderr** = the conversation -- progress, status, warnings, errors.
  Always goes to the terminal even when stdout is piped. Controlled by verbosity flags.
- **logging** = the diagnostic -- reserved for `--debug` level only. Not
  the primary UI channel. Library code uses `logging.getLogger(__name__)` and
  never touches the output channel directly.

The key design tension: stderr is the right destination for human messaging
(status, progress), but `logging` is the wrong mechanism for the primary
user-facing output because it is rate-limited by verbosity level. A `--quiet`
flag that suppresses `logger.info()` will also suppress program-output messages
that were routed through `logger.info()`.

The practical rule: if suppressing a message with `--quiet` would make the
command appear to do nothing, that message is program output and belongs on stdout.

---

### what a Printer abstraction looks like

The `Printer` class is the canonical implementation pattern for dual-console
CLI tools using Rich. It wraps two `Console` instances -- one per stream --
and provides methods that route to the correct destination.

**Core interface:**

```python
class Printer:
    def __init__(
        self,
        quiet: bool = False,
        stdout_console: Console | None = None,
        stderr_console: Console | None = None,
    ): ...

    # stdout - program output (never suppressed by --quiet)
    def out(self, *args, **kwargs) -> None: ...
    def out_json(self, data: Any, *, indent: int = 2) -> None: ...

    # stderr - human messaging (suppressed by --quiet)
    def status(self, msg: str, *args, **kwargs) -> None: ...
    def warn(self, msg: str, *args, **kwargs) -> None: ...
    def error(self, msg: str, *args, **kwargs) -> None: ...
```

The `out()` method maps to `self._stdout_console.print()`. The `status()`
method maps to `self._stderr_console.print()` and is gated by `self.quiet`.
The `error()` method maps to `self._stderr_console.print(..., style="red bold")`
and is never suppressed.

**Two-console construction:**

```python
from rich.console import Console

_stdout = Console(stderr=False, highlight=False)
_stderr = Console(stderr=True, highlight=False)
```

The `stderr=False` (the default) routes to `sys.stdout`. Both instances
inherit Rich TTY detection -- they strip ANSI when their respective streams
are not a TTY.

**Verbosity control:**

The `quiet` flag suppresses `status()` calls. In the current design, `--quiet`
maps to `logging.WARNING` via `configure_logging()`. With a `Printer`,
`--quiet` should additionally set `printer.quiet = True`, so both channels
respect the flag. This requires `setup_logging()` in `cli_common.py` to also
instantiate and configure the `Printer`.

---

### class vs module-level functions

**Class approach (recommended):**

- Instantiated once in the CLI entry point after argument parsing:
  `printer = Printer(quiet=args.quiet)`
- Passed to command handlers, or attached to `args` namespace
  (`args.printer = printer`)
- Testable: inject `Printer(stdout_console=Console(file=StringIO()))` in tests
- Thread-safe: each `Printer` owns its own `Console` instances, which are
  themselves thread-safe for print calls (Rich uses a lock internally)
- Supports subclassing (e.g., a `CapturingPrinter` for tests backed by `StringIO`)

**Module-level singleton approach:**

- `printer = get_printer()` -- a module-level singleton initialized lazily
- Simpler call sites (no argument threading)
- Harder to test (requires resetting global state between tests, same
  problem as the existing `_logging_configured` flag)

**Verdict:** Class approach. The existing codebase already threads `args`
through all command handlers; attaching `args.printer` after `setup_logging()`
in `cli_common.py` follows the existing initialization pattern exactly.

---

### `--json` and `--format` flag handling

The codebase already has `--json` flags in `vault_cli.py` (audit, index, search)
and `spec_cli.py` (readiness). Current pattern:
`if args.json: print(json.dumps(results)) else: print(table)`.

With a `Printer`, the `--json` flag changes behavior at two levels:

1. `printer.out_json(data)` -- formats and emits JSON to stdout via the stdout Console
2. `printer.quiet = True` (implied) -- suppresses `status()` stderr messages
   so JSON consumers get clean stdout

This is the pattern used by ruff (`--output-format=json`) and cargo
(`--message-format=json`). The key insight: `--json` implies `--quiet` for
the purposes of the Printer, even if the `--quiet` flag was not passed.

A richer `--format` flag (supporting `text`, `json`, `csv`) can be layered
onto `Printer.out_json()` later without changing the call sites.

---

### incremental migration strategy

A big-bang rewrite touching all 50+ `print()` call sites at once is high risk.
The recommended approach is additive migration in three sub-phases:

**Sub-phase A: infrastructure only**

Add `Printer` class to a new module (`src/vaultspec/printer.py`). Extend
`setup_logging()` in `cli_common.py` so it also instantiates a `Printer` and
attaches it to `args`:

```python
args.printer = Printer(quiet=getattr(args, "quiet", False))
```

No call sites change yet. Zero behavioral difference.

**Sub-phase B: fix inconsistencies (targeted)**

Fix the specific anti-patterns identified in the audit:

1. `hooks_list()` empty-state: change `logger.info(...)` to `printer.out(...)`
   -- both states now go to stdout
2. `handle_search()` empty-state: change `logger.info(...)` to `printer.out(...)`
   -- results and no-results both go to stdout
3. `handle_index()` summary table: change `logger.info(...)` to `printer.out(...)`
   -- the index results are program output
4. `init_run()` duplicate: remove the `logger.info()` mirror of `print()` calls
5. `orchestration/subagent.py` f-strings: convert to `%s` lazy format
   at lines 261, 269, 492

This sub-phase touches approximately 10 call sites. Each is a targeted, justified fix.

**Sub-phase C: systematic migration (optional, incremental)**

Migrate remaining `print()` calls to `printer.out()` at leisure. This is
mechanical and can be done command-by-command. Not urgent -- `print()` to
stdout is already correct behavior; `printer.out()` just adds TTY awareness
and style options for future enhancements (color, markup).

---

### when logger.info() stays in CLI code

The research question: should CLI-layer `logger.info()` calls be replaced by
`printer.status()` or kept as-is?

**Arguments for keeping `logger.info()` in CLI code:**

- The RichHandler already routes `logger.info()` to stderr correctly (Phase 1)
- Verbosity ladder (`--quiet` to WARNING) already suppresses `logger.info()`
  as intended for status messages
- Status messages (Syncing rules..., Done.) are correctly suppressible
- 30+ module-level loggers use the canonical pattern -- consistency argument

**Arguments for replacing with `printer.status()`:**

- Makes channel intent explicit at the call site (status vs program output)
- Allows richer formatting (progress spinners, styled status) without touching the logging subsystem
- Separates what the user sees from what gets logged

**Verdict:** The status messages in CLI handlers (`logger.info("Syncing...")`,
`logger.info("Done.")`) are fine as-is. They correctly map to the logging
layer purpose. Only the call sites where `logger.info()` is producing program
output (search empty-state, index summary, hooks empty-state) need to change.
Library-internal `logger.*()` calls in `core/sync.py`, `orchestration/`,
`protocol/` must not be changed.

---

### MCP server interaction

`mcp_server/app.py` uses stdio transport (`mcp.run()` defaults to stdio). Any
output to stdout corrupts the JSON-RPC framing. Current state:

- No `configure_logging()` call -- the root logger default handler at WARNING
  level means `logger.info()` calls are silently dropped. Accidental safety.
- `logger.info("Starting vaultspec-mcp server root=%s", root_dir)` is the
  only logging call -- at INFO level, never visible under default config.

The `Printer` must never be instantiated in the MCP server context. MCP tool
handlers that want to log use the module-level `logger = logging.getLogger(__name__)`
which routes to stderr via the logging subsystem. The `SubagentClient` (used
by MCP server to dispatch agents) already uses `_console = Console(stderr=True)` --
it never touches stdout. This is already correct and must be preserved.

---

### agent feed Console interaction

`src/vaultspec/protocol/acp/client.py` has a module-level
`_console = Console(stderr=True, highlight=False)` used for streaming agent content:

- `ToolCallStart`: `_console.print(f"({update.title})", style="dim")`
- `AgentMessageChunk`: `_console.print(text, end="")`
- `AgentThoughtChunk`: `_console.print(text, style="italic", end="")`

This is independent of the `Printer` abstraction -- it is the streaming
agent feed, not CLI program output. It remains as a separate module-level
console, not integrated into `Printer`.

The `Printer` and `client.py` `_console` share the same `stderr=True`
destination but serve different purposes:

- `client.py._console`: streaming agent content (raw, no timestamps)
- `Printer._stderr_console`: CLI status messages (potentially styled differently)

Both can coexist. They do not interfere because Rich `Console` instances are
independent -- each has its own lock and buffer. The only coordination needed:
if a `Printer.status()` message and an agent chunk both emit to stderr
simultaneously in an async context, they may interleave. This is an acceptable
trade-off for now; a future phase could use Rich live displays to handle this cleanly.

---

### testability

The `print()` call sites are currently tested via `capsys` (pytest
stdout/stderr capture). The `Printer` class supports testability by accepting
`Console` instances backed by `StringIO`:

```python
from io import StringIO
from rich.console import Console

out = StringIO()
err = StringIO()
printer = Printer(
    stdout_console=Console(file=out, highlight=False),
    stderr_console=Console(file=err, highlight=False),
)
```

This pattern avoids the `capsys` dependency and makes test assertions explicit
about which stream content appeared on. The no-mock constraint is satisfied:
`Printer` is a real object injected with real `Console` instances backed by
real `StringIO` streams. No stubbing needed.

---

### summary of findings mapped to research questions

**Q1: Printer API shape**

Minimal surface: `out()`, `out_json()`, `status()`, `warn()`, `error()`.
`out()` to stdout always. `status()` to stderr, suppressible by `quiet`.
`warn()` and `error()` to stderr, never suppressed. Constructor accepts
optional `Console` overrides for testability.

**Q2: Class or module-level functions**

Class. Instantiated once per CLI invocation after argument parsing, attached
to `args.printer`. Supports injection in tests without global state resets.

**Q3: `--json` / `--format` handling**

`--json` sets `printer.quiet = True` (implied suppression) and routes all
program output through `printer.out_json()`. Can be extended to a richer
`--format` flag without changing call sites.

**Q4: Incremental migration**

Three sub-phases: A (infrastructure only, no behavioral change), B (fix
approximately 10 inconsistent call sites), C (optional systematic migration of
remaining `print()` calls). Sub-phase B is the highest-value change.

**Q5: `logger.info()` in CLI code: keep or replace**

Keep status messages as `logger.info()`. Replace only the call sites where
`logger.info()` is producing program output (search empty-state, index summary,
hooks empty-state). Library modules untouched.

**Q6: `get_console()` and RichHandler fate**

Both stay. `get_console()` provides the shared stderr console for `RichHandler`.
`Printer` creates independent `Console` instances. No conflict.

**Q7: MCP server**

`Printer` never instantiated in MCP server path. MCP tool handlers use
`logger.*()` only. The `mcp.run()` stdio transport is safe as long as nothing
writes to stdout outside the JSON-RPC framing.

**Q8: Agent feed Console**

`client.py` module-level `_console` remains independent. No integration with
`Printer`. Both are `Console(stderr=True)` instances and can coexist.

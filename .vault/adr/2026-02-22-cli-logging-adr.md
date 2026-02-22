---
# ALLOWED TAGS - DO NOT REMOVE
# REFERENCE: #adr #audit #exec #plan #reference #research #{feature}
tags:
  - "#adr"
  - "#cli-logging"
date: "2026-02-22"
related:
  - "[[2026-02-22-cli-logging-research]]"
---

# `cli-logging` adr: unified Rich-based CLI and agent feed logging | (**status:** `accepted`)

## Problem Statement

vaultspec's 5 CLI entry points and agent feed output use plain stdlib
`logging.StreamHandler` with no color, no TTY detection, and inconsistent
verbosity controls. Agent output (`[tool] Read (toolu_01ABC...)`,
`[agent] ...`, `[thought] ...`) is noisy, unstyled, and indistinguishable
across message types. Claude and Gemini feeds have no visual parity despite
converging at the same `SubagentClient` callback layer.

## Considerations

- **Rich vs structlog vs loguru** — Rich plugs into stdlib `logging` as a
  drop-in handler. structlog requires a new processor pipeline; loguru uses a
  global singleton that composes poorly with hierarchical loggers. All 30+
  modules already use `logging.getLogger(__name__)`.
- **TTY awareness** — piped/CI output must remain plain text. Rich auto-strips
  ANSI when `isatty()` is `False`, but we also need a plain `Formatter`
  fallback for non-TTY stderr.
- **Callback architecture** — `SubagentClient` already accepts
  `on_message_chunk`, `on_thought_chunk`, `on_tool_update` callbacks. Agent
  feed formatting can be applied at the callback level without touching the
  protocol layer.
- **stdout vs stderr** — `print()` calls in `core/commands.py` are program
  output (stdout). Logging goes to stderr. This separation is correct and must
  be preserved.

## Constraints

- Python 3.13+ (project minimum)
- `rich` is the only new dependency (~3MB, MIT, Textualize)
- Must not break pytest log capture (`log_cli` config in `pyproject.toml`)
- Must not alter JSONL session audit logs (`SessionLogger`)
- `subagent_cli` uses `%(message)s` format intentionally — preserve this
- MCP server (`vaultspec-mcp`) runs over stdio — must not emit ANSI on stdout

## Implementation

### Phase 1: CLI logging infrastructure

**`logging_config.py`** — rewrite `configure_logging()`:

- When `sys.stderr.isatty()`: use `rich.logging.RichHandler` with
  `rich_tracebacks=True`, `markup=False`, `show_path=False`
- When not TTY: use plain `logging.StreamHandler(sys.stderr)` with the
  existing format string
- Accept a `quiet` parameter that sets level to `WARNING`
- Preserve idempotency guard and `reset_logging()` for tests

**`cli_common.py`** — update `add_common_args()` and `setup_logging()`:

- Add `--quiet`/`-q` flag (mutually exclusive with `--verbose`/`--debug`)
- Verbosity ladder: `--quiet` → WARNING, default → INFO, `-v` → INFO
  (explicit), `--debug` → DEBUG
- Pass `quiet` through to `configure_logging()`

**`pyproject.toml`** — add `rich>=13.0.0` to `dependencies`

**`__main__.py`** — no changes needed; sub-CLIs call `setup_logging(args)`
individually

### Phase 2: Agent feed formatting

**`protocol/acp/client.py`** — update fallback logging in
`_handle_content_chunk()`:

- Tool calls: replace `logger.info("[tool] %s (%s)", title, id)` with
  dim-styled `(tool_name) message` via Rich `Console`. Drop the tool call ID.
- Agent messages: replace `logger.info("[agent] %s", text)` with unstyled
  `console.print(text, end="")` (no prefix, normal color).
- Agent thinking: replace `logger.debug("[thought] %s", text)` with
  italic-styled `console.print(text, style="italic", end="")` (no prefix).

**Shared `Console` instance** — create a module-level
`Console(stderr=True, highlight=False)` in `client.py` for direct styled
output. This bypasses the logging framework intentionally: agent feed is
*streaming content*, not log records.

**Callback passthrough** — when callbacks (`on_message_chunk`, etc.) are
provided by `orchestration/subagent.py`, the callbacks handle formatting.
The Rich styling in `client.py` only applies to the no-callback fallback path.

**Claude/Gemini parity** — both providers emit `AgentMessageChunk`,
`AgentThoughtChunk`, and `ToolCallStart` through the same
`SubagentClient._handle_content_chunk()`. A single formatting layer gives
both providers identical visual treatment with zero provider-specific code.

### Visual spec

```
# Tool call — dim, parenthesized name, no ID
(Read) src/vaultspec/logging_config.py

# Agent thinking — italic, no prefix
Let me analyze the logging configuration...

# Agent response — normal color, no prefix
The logging module uses a centralized configure_logging() function.
```

## Rationale

- **Rich `RichHandler`** is the only option that requires zero changes to 30+
  module-level loggers while providing colorized output, TTY detection, and
  rich tracebacks. See [[2026-02-22-cli-logging-research]] for the full
  library comparison.
- **Direct `Console.print()` for agent feed** (instead of logging) is correct
  because agent output is *streaming content*, not structured log records.
  Using logging would force each chunk through the handler pipeline with
  timestamps and levels, destroying the streaming UX.
- **Single convergence point** at `SubagentClient` eliminates the need for
  provider-specific formatting and guarantees Claude/Gemini visual parity.
- **`--quiet` flag** follows the standard Unix CLI pattern (see research) and
  fills the gap between default INFO and `--debug`.

## Consequences

- **New dependency**: `rich>=13.0.0` added to core `dependencies` (not
  optional). This is acceptable — Rich is widely adopted and vaultspec is a
  CLI tool, not a library.
- **Visual diff in output**: existing users/scripts parsing plain-text log
  output will see ANSI codes in TTY mode. Non-TTY (piped) output is unchanged.
- **Phase 2 bypasses logging for agent feed**: tool calls, thinking, and
  responses use `Console.print()` directly. This means these messages won't
  appear in `logging`-based captures (e.g., pytest `caplog`). Tests should
  use the callback interface instead.
- **Future phases** can leverage Rich `Console` for progress bars, tables,
  and status spinners in CLI commands (e.g., `vault index`, `vault audit`).

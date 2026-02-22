---
# ALLOWED TAGS - DO NOT REMOVE
# REFERENCE: #adr #audit #exec #plan #reference #research #{feature}
tags:
  - "#research"
  - "#cli-logging"
date: "2026-02-22"
related: []
---

# `cli-logging` research: standardize CLI logging with Rich

Research into current logging patterns across all vaultspec CLI entry points and
best modern practices for Python CLI logging. Phase 1 focuses on the CLI layer
only; phase 2 (subagent/team logging formatting) is out of scope.

## Findings

### Current state

**Entry points** (5 CLIs, all via `pyproject.toml [project.scripts]`):

| Script              | Module                        | Logging setup call              |
|---------------------|-------------------------------|---------------------------------|
| `vaultspec`         | `__main__:main`               | Routes to sub-CLIs              |
| `vaultspec vault`   | `vault_cli:main`              | `setup_logging(args)`           |
| `vaultspec team`    | `team_cli:main`               | `setup_logging(args)`           |
| `vaultspec subagent`| `subagent_cli:main`           | `setup_logging(args, fmt=...)` |
| `vaultspec-mcp`     | `mcp_server.app:main`         | No logging setup                |
| (spec commands)     | `spec_cli:main`               | `configure_logging()` + `setup_logging(args)` |

**Shared infrastructure** — `cli_common.py`:

- `add_common_args()`: adds `--verbose`, `--debug`, `--root`, `--content-dir`
- `setup_logging(args)`: calls `logging_config.configure_logging()` with
  level derived from `args.debug` / `args.verbose`
- `run_async()`: async runner with Windows-safe teardown
- `cli_error_handler()`: context manager for clean error exit

**`logging_config.py`**:

- Single `configure_logging()` function with idempotency guard
- Uses `logging.StreamHandler(sys.stderr)` — correct stderr destination
- Format: `%(asctime)s [%(name)s] %(levelname)s: %(message)s`
- Default level: `INFO` (from env `VAULTSPEC_LOG_LEVEL`)
- `reset_logging()` for tests

**Problems identified**:

- **No color or formatting** — plain text output in all terminals
- **Mixed output channels** — `core/commands.py` and `core/agents.py` use raw
  `print()` (stdout) for structured data, while errors go through `logger`
  (stderr). This is *correct* for program output vs. logging, but the logging
  side lacks visual distinction.
- **Inconsistent defaults** — `spec_cli.py` calls both `configure_logging()`
  and `setup_logging(args)` (double initialization, saved by idempotency)
- **`subagent_cli.py`** passes a custom `default_format="%(message)s"` to strip
  metadata from subagent output — this is intentional and should be preserved
- **No TTY detection** — piped output gets the same format as interactive
- **No `-q`/`--quiet` flag** — only `-v` and `--debug` exist
- **`mcp_server/app.py`** does no logging setup at all

### Module-level logger usage (correct pattern)

All 30+ modules use `logger = logging.getLogger(__name__)` — the canonical
pattern. No module calls `basicConfig()` or configures handlers directly.

### Library recommendation: Rich `RichHandler`

Rich is the strongest fit for vaultspec:

- **Drop-in replacement**: plugs into stdlib `logging`, zero changes needed to
  module-level loggers
- **TTY-aware**: automatically strips ANSI when piped
- **Colorized levels**, syntax-highlighted tracebacks, time columns
- **Also provides** `Console`, `Progress`, `Status` for future CLI UX (phase 2)
- **No new paradigm** — structlog and loguru would require rethinking the
  logging hierarchy
- Rich is ~3MB, well-maintained (Textualize), and widely adopted

### Design decisions needed

- **`-q`/`--quiet` flag**: should map to `WARNING` (suppress `INFO`)
- **TTY fallback**: when `stderr.isatty()` is `False`, use plain `Formatter`
- **`RichHandler` config**: `rich_tracebacks=True`, `markup=False` (safety),
  `show_path=False` (clean output)
- **`print()` output** in `core/commands.py`: this is *program output* (stdout),
  not logging — should remain as-is for phase 1. Phase 2 may migrate some to
  Rich `Console`.
- **subagent_cli**: preserve `%(message)s` format for clean agent output
- **Test impact**: `pytest` has its own `log_cli` config in `pyproject.toml` —
  `RichHandler` should not interfere since pytest captures logging independently

### Migration scope (phase 1)

Files to modify:

- `logging_config.py` — add Rich-aware handler, TTY detection
- `cli_common.py` — add `--quiet`/`-q` flag, update `setup_logging()`
- `pyproject.toml` — add `rich` to dependencies
- `__main__.py` — ensure logging is initialized before sub-CLI dispatch
- No changes to module-level loggers (all 30+ files stay as-is)

---

## Phase 2: Agent feed formatting

### Current agent output formatting

All user-visible agent output originates from a single file:
`src/vaultspec/protocol/acp/client.py` (the `SubagentClient`).

Three message types are logged with prefix-based formatting:

| Type         | Current format                          | Log level | Line |
|--------------|----------------------------------------|-----------|------|
| Tool call    | `[tool] {name} ({tool_call_id})`       | INFO      | 246  |
| Agent msg    | `[agent] {text}`                       | INFO      | 269  |
| Thinking     | `[thought] {text}`                     | DEBUG     | 276  |

**Callback architecture**: `SubagentClient` accepts three optional callbacks
(`on_message_chunk`, `on_thought_chunk`, `on_tool_update`). When callbacks are
set, they are invoked instead of logging. When absent, the logger fallback
fires. This means formatting can be customized at the callback level without
touching the protocol layer.

### Output flow

```
Claude Executor / Gemini Executor
    |
ACP Bridge (claude_bridge.py / gemini_bridge.py)
    | emit session_update notifications
SubagentClient (client.py)
    |--- callbacks (if provided): on_message_chunk / on_thought_chunk / on_tool_update
    |--- fallback: logger.info("[agent]...") / logger.debug("[thought]...") / logger.info("[tool]...")
    |
SessionLogger -> JSONL audit trail
```

### Problems with current formatting

- **`[tool] Read (toolu_01ABC123DEF)`** — the tool call ID is a long opaque
  string that adds noise. Users don't need it.
- **`[agent]` prefix on every message chunk** — redundant when streaming
  continuously; clutters the feed.
- **`[thought]` at DEBUG level** — invisible unless `--debug` is set, and when
  visible, it's indistinguishable from other debug noise.
- **No color differentiation** — tool calls, agent text, and thinking all render
  identically in the terminal.
- **Claude vs Gemini parity gap** — Claude streams fine-grained deltas
  (`text_delta`, `thinking_delta`, `input_json_delta`) through the bridge.
  Gemini proxies child session updates transparently. Both converge at
  `SubagentClient` callbacks, so the formatting layer is unified, but the
  *visual output* has no distinction between providers.

### Desired formatting (user-specified)

| Type          | Format                         | Style                    |
|---------------|--------------------------------|--------------------------|
| Tool call     | `(tool_name) Message`          | Dim text, no index/ID    |
| Agent thinking| `{text}` (no prefix)           | Italic, not dimmed       |
| Agent response| `{text}` (no prefix)           | Normal color             |

### Where to implement

The callback-based architecture makes this clean:

- **`client.py`** fallback logging: update the three `logger.*()` calls to use
  Rich markup or a custom `Formatter`
- **`orchestration/subagent.py`**: when providing callbacks to
  `SubagentClient`, format with Rich `Console` styles
- **Both providers converge at `SubagentClient`** — a single formatting layer
  achieves Claude/Gemini visual parity automatically

### Rich styling primitives

```python
from rich.console import Console
console = Console(stderr=True)

# Tool call — dim
console.print(f"({tool_name}) {message}", style="dim")

# Thinking — italic
console.print(text, style="italic")

# Agent response — default (no style override)
console.print(text)
```

### Parity considerations

Since both Claude and Gemini output converges at `SubagentClient._handle_content_chunk()`,
applying Rich formatting there (or in the callbacks set by `orchestration/subagent.py`)
automatically gives both providers identical visual treatment. No provider-specific
formatting code is needed.

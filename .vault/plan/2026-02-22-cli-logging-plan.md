---
# ALLOWED TAGS - DO NOT REMOVE
# REFERENCE: #adr #audit #exec #plan #reference #research #{feature}
tags:
  - "#plan"
  - "#cli-logging"
date: "2026-02-22"
related:
  - "[[2026-02-22-cli-logging-adr]]"
  - "[[2026-02-22-cli-logging-research]]"
---

# `cli-logging` plan

Standardize all CLI logging with Rich and overhaul agent feed formatting for
colorized, readable output. Implements [[2026-02-22-cli-logging-adr]].

## Proposed Changes

Two phases. Phase 1 replaces the plain `StreamHandler` with a TTY-aware
`RichHandler` across all CLI entry points and adds a `--quiet` flag. Phase 2
rewrites agent feed output in `SubagentClient` to use styled Rich `Console`
output — dim tool calls, italic thinking, unstyled responses — achieving
Claude/Gemini visual parity through the shared callback convergence point.

## Tasks

- Phase 1: CLI logging infrastructure
    1. Add `rich>=13.0.0` dependency to `pyproject.toml`
    2. Rewrite `logging_config.py` — TTY-aware handler selection
    3. Update `cli_common.py` — `--quiet` flag, verbosity ladder
    4. Fix `spec_cli.py` double-init — remove redundant `configure_logging()`
    5. Install rich and verify import works
- Phase 2: Agent feed formatting
    1. Add Rich `Console` to `protocol/acp/client.py` and restyle output
    2. Verify `orchestration/subagent.py` callback path is unaffected
    3. Run existing tests to confirm no regressions

### Phase 1 detail

**Step 1 — `pyproject.toml`**

- File: `pyproject.toml`
- Add `"rich>=13.0.0"` to `dependencies` list (after `PyYAML`)

**Step 2 — `logging_config.py`**

- File: `src/vaultspec/logging_config.py`
- Rewrite `configure_logging()`:
  - Add `quiet: bool = False` parameter
  - Level ladder: `debug` → DEBUG, `quiet` → WARNING, `level` param → as
    given, env `VAULTSPEC_LOG_LEVEL` → as given, fallback → INFO
  - When `sys.stderr.isatty()`: create `RichHandler(rich_tracebacks=True,
    markup=False, show_path=False, show_time=True, show_level=True)`
  - When not TTY: create plain `StreamHandler(sys.stderr)` with existing
    format `"%(asctime)s [%(name)s] %(levelname)s: %(message)s"`
  - When `log_format` is explicitly passed (subagent_cli case): always use
    plain `StreamHandler` with that format, even in TTY — this preserves
    the `%(message)s` clean-output mode for agent streaming
  - Preserve idempotency guard (`_logging_configured`)
  - Preserve `reset_logging()` unchanged
- Export: add `"get_console"` to `__all__` — a lazy accessor that returns
  a module-level `Console(stderr=True, highlight=False)` singleton for use
  by phase 2

**Step 3 — `cli_common.py`**

- File: `src/vaultspec/cli_common.py`
- `add_common_args()`: replace the current `--verbose` and `--debug` with a
  mutually exclusive group containing `--verbose`/`-v`, `--debug`, and
  `--quiet`/`-q`
- `setup_logging()`: read `getattr(args, "quiet", False)` and pass it
  through to `configure_logging(quiet=...)`

**Step 4 — `spec_cli.py`**

- File: `src/vaultspec/spec_cli.py`
- Remove the bare `configure_logging()` call at `main()` line 59 — this is
  redundant because `setup_logging(args)` is called at line 259 after arg
  parsing. The early call currently locks in INFO before CLI flags are
  processed (saved only by idempotency skipping the second call).

**Step 5 — Install and verify**

- Run `pip install -e .` to install the new `rich` dependency
- Verify `python -c "from rich.logging import RichHandler; print('ok')"`

### Phase 2 detail

**Step 1 — `protocol/acp/client.py`**

- File: `src/vaultspec/protocol/acp/client.py`
- Add import: `from rich.console import Console`
- Create module-level console: `_console = Console(stderr=True, highlight=False)`
- In `session_update()` (around line 242-246), replace the `ToolCallStart`
  fallback:
  - Old: `logger.info("[tool] %s (%s)", update.title, update.tool_call_id)`
  - New: `_console.print(f"({update.title})", style="dim", end=" ")` followed
    by printing any tool message content if available, also dim. No tool call
    ID.
- In `_handle_content_chunk()` (around line 265-276):
  - `AgentMessageChunk` fallback — old: `logger.info("[agent] %s", text)`.
    New: `_console.print(text, end="", highlight=False)` (no prefix, normal
    color)
  - `AgentThoughtChunk` fallback — old: `logger.debug("[thought] %s", text)`.
    New: `_console.print(text, style="italic", end="")` (no prefix, italic)
- Guard all `_console.print()` calls behind `not self.quiet` (same as current)
- TTY safety: `Console(stderr=True)` already handles non-TTY by stripping
  ANSI automatically

**Step 2 — Verify callback passthrough**

- File: `src/vaultspec/orchestration/subagent.py`
- Read-only verification: confirm that when callbacks are provided, the new
  `_console.print()` paths are never reached (existing `if self.on_*`
  short-circuits). No code changes expected.

**Step 3 — Run tests**

- Run `pytest src/vaultspec/protocol/acp/tests/ -x` — confirm ACP client
  tests pass
- Run `pytest src/vaultspec/config/tests/ -x` — confirm config tests pass
- Run `pytest tests/test_config.py -x` — confirm top-level config test
- Quick smoke: `vaultspec --help`, `vaultspec doctor`, `vaultspec vault audit
  --summary` — confirm Rich-formatted output in terminal

## Parallelization

Phase 1 steps 1-4 are sequential (each depends on the previous). Phase 2
step 1 depends on phase 1 being complete (Rich must be installed). Phase 2
steps 2-3 can run in parallel after step 1.

Overall: **strictly sequential** — this is a small, focused refactor best
handled by a single executor.

## Verification

- All existing tests pass without modification (30+ modules untouched)
- `vaultspec --help` shows unformatted output (no logging involved)
- `vaultspec vault audit --summary` shows Rich-formatted log output in TTY,
  plain text when piped (`vaultspec vault audit --summary 2>/dev/null`)
- `vaultspec subagent run --agent ... --goal ...` shows styled agent feed:
  dim tool calls, italic thinking, normal responses
- `--quiet` suppresses INFO-level messages
- `--debug` shows DEBUG-level with full context
- `VAULTSPEC_LOG_LEVEL=WARNING vaultspec ...` respects env override
- pytest log capture (`log_cli = true`) continues to work as configured

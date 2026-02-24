---
tags:
  - "#exec"
  - "#cli-logging"
date: "2026-02-22"
related:
  - "[[2026-02-22-cli-logging-plan]]"
  - "[[2026-02-22-cli-logging-adr]]"
  - "[[2026-02-22-cli-logging-research]]"
---
# `cli-logging` execution summary

Implemented unified Rich-based CLI logging and agent feed formatting across
all vaultspec entry points.

- Modified: `pyproject.toml`
- Modified: `src/vaultspec/logging_config.py`
- Modified: `src/vaultspec/cli_common.py`
- Modified: `src/vaultspec/spec_cli.py`
- Modified: `src/vaultspec/protocol/acp/client.py`

## Description

**Phase 1 — CLI logging infrastructure:**

- Added `rich>=13.0.0` as a core dependency
- Rewrote `logging_config.py` with TTY-aware handler selection: `RichHandler`
  for interactive terminals (colorized levels, rich tracebacks), plain
  `StreamHandler` for pipes/CI. Added `get_console()` singleton for phase 2.
- Added `--quiet`/`-q` flag to `cli_common.py` in a mutually exclusive group
  with `--verbose` and `--debug`. Verbosity ladder: quiet→WARNING,
  default→INFO, verbose→INFO (explicit), debug→DEBUG.
- Fixed `spec_cli.py` double-init bug (removed redundant `configure_logging()`
  call that locked in INFO before CLI flags were parsed).

**Phase 2 — Agent feed formatting:**

- Restyled `SubagentClient` fallback output in `client.py`:
  - Tool calls: `(tool_name)` in dim (no ID, no index)
  - Agent thinking: italic, no prefix
  - Agent responses: normal color, no prefix
- Claude/Gemini visual parity achieved through the shared `SubagentClient`
  convergence point — zero provider-specific code.

## Tests

- Config tests: 183 passed
- CLI tests: 175 passed
- ACP protocol tests: 423 passed
- Smoke: `vaultspec --help` renders correctly
- No test modifications required (all 30+ module-level loggers untouched)

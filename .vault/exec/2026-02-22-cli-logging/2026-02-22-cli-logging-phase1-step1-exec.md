---
tags:
  - "#exec"
  - "#cli-logging"
date: "2026-02-22"
related:
  - "[[2026-02-22-cli-logging-plan]]"
---
# `cli-logging` phase-1 step-1

Phase 1: CLI logging infrastructure — add Rich dependency, rewrite
logging_config.py with TTY-aware RichHandler, add --quiet flag, fix
spec_cli.py double-init.

- Modified: `pyproject.toml`
- Modified: `src/vaultspec/logging_config.py`
- Modified: `src/vaultspec/cli_common.py`
- Modified: `src/vaultspec/spec_cli.py`

## Description

- Added `rich>=13.0.0` to `pyproject.toml` dependencies
- Rewrote `logging_config.py`: TTY detection via `sys.stderr.isatty()`,
  `RichHandler` for interactive terminals (with `rich_tracebacks=True`,
  `markup=False`, `show_path=False`), plain `StreamHandler` for pipes/CI.
  Added `quiet` parameter, `get_console()` singleton accessor. Preserved
  idempotency guard and `reset_logging()`.
- Updated `cli_common.py`: `--verbose`/`--debug`/`--quiet` in a mutually
  exclusive group. `setup_logging()` passes `quiet` through.
- Removed redundant `configure_logging()` import and call from `spec_cli.py`
  (double-init bug).
- Installed via `uv sync`.

## Tests

- Config tests: 183 passed
- CLI tests: 175 passed
- Smoke: `vaultspec --help` works correctly

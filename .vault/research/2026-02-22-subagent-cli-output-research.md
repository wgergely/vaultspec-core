---
tags: ["#research", "#subagent-cli"]
related: []
date: 2026-02-22
---

# Subagent CLI Output & Stability Research

## Objective
Improve the output formatting of `subagent_cli.py` to be less noisy and fix the `ValueError: I/O operation on closed pipe` error observed on Windows.

## Current State

### Logging
- **Config:** `src/vaultspec/logging_config.py`
- **Format:** `%(asctime)s [%(name)s] %(levelname)s: %(message)s`
- **Issue:** Too verbose for CLI users. Displays timestamps and logger names for every message.

### Windows Pipe Error
- **Error:** `ValueError: I/O operation on closed pipe`
- **Context:** `asyncio` with `ProactorEventLoop` on Windows.
- **Trigger:** `_ProactorBasePipeTransport.__del__` logs a `ResourceWarning`, which triggers `__repr__`, which calls `fileno()`, which fails because the pipe is closed.
- **Root Cause:** Asynchronous generators or transports not being strictly closed before the event loop is closed, or garbage collection triggering `__del__` after loop closure.

## Findings & Strategy

### 1. Logging Improvements
- Modify `configure_logging` to accept a `format_string` or a `simple` flag.
- Update `subagent_cli.py` to use a minimal format (e.g., `"%(message)s"`) unless `--verbose` or `--debug` is used.

### 2. Fixing Pipe Error
The error usually stems from `ResourceWarning` being emitted during garbage collection of unclosed transports.
- **Fix A (Suppress):** Extend the `warnings` suppression scope.
- **Fix B (Cleanup):** Ensure `loop.run_until_complete(asyncio.sleep(0.1))` is called before closing the loop to allow pending callbacks to fire.
- **Fix C (Event Loop Policy):** Since `ProactorEventLoop` is the default and required for subprocesses, we can't easily switch.
- **Recommended:** Add a small sleep before loop close and ensure `ResourceWarning` is ignored globally for the CLI session if needed.

## Proposed Changes

1.  **`src/vaultspec/logging_config.py`**:
    - Add `log_format` parameter.

2.  **`src/vaultspec/subagent_cli.py`**:
    - Update `configure_logging` call.
    - Add `loop.run_until_complete(asyncio.sleep(0.1))` before `loop.close()`.
    - Wrap the `main` or loop logic in a broader `warnings.catch_warnings()` block?
    - Actually, the traceback shows the error happening *during* `_warn`.
    - Best approach: `asyncio.set_event_loop(None)` before closing? No.
    - We will try the "sleep" hack first, as it's the least intrusive standard fix for this Windows issue.

## Validation Plan
- Run `python src/vaultspec/subagent_cli.py run ...` and verify output format.
- Verify if the pipe error persists (might be hard to reproduce deterministically without the exact workload, but "sleep" is a known prophylactic).

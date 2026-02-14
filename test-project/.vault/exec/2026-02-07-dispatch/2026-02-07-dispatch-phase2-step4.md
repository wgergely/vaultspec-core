---
feature: dispatch
phase: phase2
step: 4
date: 2026-02-07
---

# Step 4: Convert dispatch_agent to Async Dispatch

## Summary

Refactored `dispatch_agent` from synchronous (blocking) to asynchronous (fire-and-forget) dispatch. The tool now returns immediately with a `taskId` while the sub-agent runs in the background.

## Implementation Details

### Changes to `mcp_dispatch.py`

1. **`dispatch_agent` refactored:** Creates a `DispatchTask` in the engine (status: working), spawns `_run_dispatch_background()` via `asyncio.create_task()`, returns immediately with `{taskId, status, agent, model, mode}`.

2. **`_run_dispatch_background()` added:** Async helper that:
   - Calls `run_dispatch()` (ACP layer)
   - On success: calls `task_engine.complete_task()` with structured result per ADR schema
   - On `asyncio.CancelledError`: logs cancellation (engine state already set by `cancel_task`)
   - On `AgentNotFoundError`/`DispatchError`: calls `task_engine.fail_task()`
   - On unexpected `Exception`: calls `task_engine.fail_task()` with generic error

3. **`_background_tasks` dict:** Maps `task_id -> asyncio.Task` for tracking in-flight dispatches. Cleaned up via `add_done_callback` when background task finishes.

4. **`cancel_task` enhanced:** Now also cancels the background asyncio task (`bg_task.cancel()`) in addition to updating engine state.

### Test Updates

- `test_missing_agent_returns_failed` -> split into `test_async_dispatch_returns_working` and `test_missing_agent_fails_in_background`
- `test_response_structure_on_error` -> `test_response_structure_async` (checks for taskId, model, mode)
- `test_task_file_resolution` updated to use `get_task_status` for error verification
- `test_valid_modes_accepted` updated to check for `working` status
- Total: 14 tests, all passing

## Files Modified

- `.rules/scripts/mcp_dispatch.py`
- `.rules/scripts/tests/test_mcp_dispatch.py`

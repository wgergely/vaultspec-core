---
feature: dispatch
phase: phase4
step: 5
date: 2026-02-07
status: complete
related:
  - "[[2026-02-07-dispatch-phase4-plan]]"
  - "[[2026-02-07-dispatch-phase4-step4]]"
---

# Step 5: Integrate Lock Release with Task Lifecycle

## Changes

### `task_engine.py` (Engine-Layer Integration)

**TaskEngine now accepts optional LockManager:**

- `__init__` takes `lock_manager: LockManager | None = None`
- New `_release_lock(task_id)` private method releases advisory lock via lock manager

**Lock release on all terminal transitions:**

- `update_status()`: releases lock when transitioning to any terminal state (covers `cancel_task()`)
- `complete_task()`: releases lock after setting COMPLETED
- `fail_task()`: releases lock after setting FAILED
- `_cleanup_expired()`: releases locks before removing expired tasks (TTL expiry path)

Lock release happens inside the `with self._lock:` block, making it atomic with the state transition.

### `mcp_dispatch.py` (MCP-Layer Integration)

1. **Lock manager passed to TaskEngine:** `lock_manager` created first, then passed to `TaskEngine(lock_manager=lock_manager)`.

2. **`finally` block in `_run_dispatch_background()`:** calls `lock_manager.release_lock(task_id)` on every exit path (completed, failed, cancelled, unexpected error).

3. **`lock_manager.release_lock(task_id)` in `cancel_task()`:** covers the race where cancel_task runs before the background task's finally block.

**Double-release safety:** `release_lock()` returns `False` if no lock exists (already released), so double-calls are harmless.

## Terminal state coverage

- `complete_task()` -> lock released by engine + finally block
- `fail_task()` (DispatchError) -> lock released by engine + finally block
- `fail_task()` (generic Exception) -> lock released by engine + finally block
- `cancel_task()` -> lock released by engine (via update_status) + explicitly + finally block
- `CancelledError` -> lock released via finally block
- TTL expiry -> lock released by engine during `_cleanup_expired()`

## Verification

- 51 task engine tests pass.
- 45 dispatch tests pass.
- Total: 96 tests pass (no regressions).

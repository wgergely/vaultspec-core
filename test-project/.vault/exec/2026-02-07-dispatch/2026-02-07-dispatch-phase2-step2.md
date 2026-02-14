---
feature: dispatch
phase: phase2
step: 2
date: 2026-02-07
---

# Step 2: Implement Internal Task Engine

## Summary

Created `.rules/scripts/task_engine.py` -- a standalone 5-state task lifecycle manager with no MCP or ACP dependencies.

## Implementation Details

### Module: `task_engine.py`

**Data Model:**

- `DispatchTask` dataclass with fields: task_id, agent, status, created_at, updated_at, model, mode, result, error, status_message.

**State Machine:**

- `TaskStatus` enum: WORKING, INPUT_REQUIRED, COMPLETED, FAILED, CANCELLED
- Terminal states: COMPLETED, FAILED, CANCELLED (no transitions allowed from these)
- Valid transitions enforced via `_VALID_TRANSITIONS` mapping
- `InvalidTransitionError` raised on illegal transitions

**TaskEngine class:**

- `create_task()` -- creates in WORKING state, returns DispatchTask
- `get_task()` -- retrieves by ID (returns None if not found/expired)
- `update_status()` -- validates transition, updates state
- `complete_task()` -- sets COMPLETED + stores structured result dict
- `fail_task()` -- sets FAILED + stores error message
- `cancel_task()` -- sets CANCELLED (rejects terminal-state tasks)
- `list_tasks()` -- returns all non-expired tasks
- `delete_task()` -- removes a task entirely
- `wait_for_update()` -- async wait with optional timeout (for polling)

**Concurrency:**

- `threading.Lock` protects dict mutations (safe from sync and async callers)
- `asyncio.Event` per task for async wait/notify pattern

**TTL Expiry:**

- Configurable TTL (default 1 hour) for terminal-state tasks
- Lazy cleanup on access (no background thread)
- Non-terminal tasks never expire

## Verification

All manual verification passed:

- Task creation, retrieval, status transitions
- Terminal state transition rejection (completed -> working blocked)
- Async wait/notify (updater wakes waiter)
- Timeout on wait_for_update
- TTL expiry for terminal tasks (working tasks preserved)

## Files

- Created: `.rules/scripts/task_engine.py`

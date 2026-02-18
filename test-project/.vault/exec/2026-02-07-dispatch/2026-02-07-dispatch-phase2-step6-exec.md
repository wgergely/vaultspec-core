---
tags:
  - "#exec"
  - "#uncategorized"
date: 2026-02-07
---
# Step 6: Write Task Engine Unit Tests

## Summary

Created comprehensive unit tests for `task_engine.py` covering all public API methods, state machine transitions, TTL expiry, async wait/notify, and concurrency.

## Test Coverage

### Test Classes (51 tests total)

| Class | Tests | Coverage |
|---|---|---|
| TestHelpers | 6 | `generate_task_id` uniqueness, `is_terminal` for all 5 states |
| TestCreateTask | 8 | Working status, UUID format, custom ID, duplicate rejection, metadata, defaults, timestamps, result/error None |
| TestGetTask | 2 | Existing task retrieval, nonexistent returns None |
| TestStateTransitions | 13 | All valid transitions (working->completed/failed/cancelled/input_required, input_required->working/completed), terminal rejection (completed/failed/cancelled->working), same-state no-op, status_message, updated_at, nonexistent raises |
| TestCompleteTask | 4 | Sets status+result, from input_required, terminal rejected, nonexistent raises |
| TestFailTask | 3 | Sets status+error, terminal rejected, nonexistent raises |
| TestCancelTask | 3 | Working task, input_required task, completed rejected |
| TestListTasks | 2 | Empty engine, lists all |
| TestDeleteTask | 2 | Existing deletion, nonexistent returns False |
| TestTTLExpiry | 4 | Terminal tasks expire, working tasks preserved, failed expires, cancelled expires |
| TestConcurrency | 1 | Multiple independent tasks tracked correctly |
| TestWaitForUpdate | 3 | Wakes on update, timeout raises, nonexistent raises |

### Design Decisions

- Used short TTL fixture (0.1s) with `time.sleep(0.2)` for expiry tests
- Used `asyncio.run()` for async tests (no pytest-asyncio dependency needed)
- Tests import directly from `task_engine` module (no MCP/ACP dependencies)
- Error message patterns verified via `pytest.raises(match=...)` for InvalidTransitionError

## Verification

```
51 passed in 1.05s
```

## Files

- Created: `.rules/scripts/tests/test_task_engine.py`

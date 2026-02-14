---
feature: dispatch
phase: phase4
step: 4
date: 2026-02-07
status: complete
related:
  - "[[2026-02-07-dispatch-phase4-plan]]"
  - "[[2026-02-07-dispatch-phase4-step3]]"
---

# Step 4: Add get_locks Tool and Lock Info to get_task_status

## Changes

### `mcp_dispatch.py`

**New `get_locks` MCP tool:**

- Returns all active advisory locks as JSON array
- Each lock entry includes: taskId, agent, paths, mode, acquired_at
- Resolves agent name from task engine for each lock
- Returns count alongside locks list

**Updated `get_task_status`:**

- Now includes `lock` object in response when the task holds an advisory lock
- Lock info shows: paths, mode, acquired_at

**Updated server instructions:**

- Added `get_locks` to the server instruction string

### `tests/test_mcp_dispatch.py`

- Updated `test_tools_registered` to assert `get_locks` is in tool list
- Updated `test_tools_count` from 4 to 5

## Verification

- All 45 dispatch tests pass (no regressions).
- All 51 task engine tests pass (no regressions).

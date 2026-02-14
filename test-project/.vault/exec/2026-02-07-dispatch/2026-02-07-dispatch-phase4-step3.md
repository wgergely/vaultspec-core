---
feature: dispatch
phase: phase4
step: 3
date: 2026-02-07
status: complete
related:
  - "[[2026-02-07-dispatch-phase4-plan]]"
  - "[[2026-02-07-dispatch-phase4-step2]]"
---

# Step 3: Enforce Permission Mode in dispatch_agent

## Changes

### `mcp_dispatch.py`

1. **Module docstring updated** to Phase 4.
2. **Imported `LockManager`** from `task_engine`.
3. **Created `lock_manager` instance** alongside `task_engine`.
4. **Added `_READONLY_PERMISSION_PROMPT`** constant with the read-only restriction text.
5. **Added `_resolve_effective_mode(agent, mode)`** -- resolves effective mode with priority: per-dispatch override > agent frontmatter default_mode > "read-write". Uses `mode is not None` check so explicit `mode="read-write"` from caller wins over agent default.
6. **Added `_inject_permission_prompt(task_content, mode)`** -- prepends permission instructions for read-only mode.
7. **Updated `dispatch_agent`**:
   - Changed `mode` parameter type from `str = "read-write"` to `str | None = None` to support agent default resolution.
   - Calls `_resolve_effective_mode()` to resolve effective mode.
   - Registers advisory lock via `lock_manager.acquire_lock()` with `.docs/` paths for read-only, `.` for read-write.
   - Injects permission prompt into task content for read-only mode.
   - Logs lock conflict warnings.
   - Passes `enforced_content` (with permission prompt) to `_run_dispatch_background`.
8. **Updated `main()` log line** to Phase 4.

**Permission prompt for read-only mode:**

```
PERMISSION MODE: READ-ONLY
You MUST only write files within the `.docs/` directory. Do not modify any source code files.
```

### `tests/test_mcp_dispatch.py`

1. **Updated `mcp_workspace` fixture** to reset `task_engine` and `lock_manager` between tests (prevents cross-test lock accumulation).
2. **Updated `test_dispatch_run_dispatch_receives_correct_args`** to explicitly pass `mode="read-write"` to avoid permission prompt injection affecting the assertion.

## Verification

- 45 dispatch tests pass (no regressions).
- 51 task engine tests pass (no regressions).
- Total: 96 tests pass.

---
tags:
  - "#exec"
  - "#dispatch"
date: 2026-02-07
related:
  - "[[2026-02-07-dispatch-task-contract]]"
  - "[[2026-02-07-dispatch-workspace-safety]]"
  - "[[2026-02-07-dispatch-architecture]]"
---

# dispatch audit code review

**Status:** PASS

## Audit Context

- **Plan:** [[2026-02-07-dispatch-phase4-plan]]
- **Scope:**
  - `.rules/scripts/mcp_dispatch.py` (bug fixes from tasks #2, #3)
  - `.rules/scripts/tests/test_mcp_dispatch.py` (new tests from task #4)
  - `.rules/scripts/tests/test_task_engine.py` (new tests from task #4)
  - `.rules/scripts/task_engine.py` (unchanged, reviewed for context)

## Findings

### Critical / High (Must Fix)

None.

### Medium / Low (Recommended)

- **[MEDIUM]** `mcp_dispatch.py:479-483`: The `finally` block in `_run_dispatch_background` now contains only `pass` with a comment. While the comment is accurate (lock release is handled by TaskEngine on terminal transitions), a bare `pass` in a `finally` block is a minor code smell. The `finally` block could be removed entirely since it serves no functional purpose. However, keeping it as documentation of the design decision is acceptable.

- **[LOW]** `mcp_dispatch.py:223-226`: The `_register_agent_resources()` function accesses `mcp._resource_manager._resources`, a private API of the FastMCP library. This is fragile and could break on library upgrades. This is pre-existing code, not introduced by the current changes.

- **[LOW]** `test_mcp_dispatch.py:508`: The `test_get_locks_returns_all` test in `test_task_engine.py:508` uses a bare `l` as a loop variable name (`ids = {l.task_id for l in locks}`), which can be confused with `1` in some fonts. This is pre-existing.

## Review Analysis

### 1. Safety & Integrity

**Panic Prevention:** N/A (Python codebase, not Rust). No unhandled exceptions in production paths. All error paths use proper try/except with `InvalidTransitionError` guards.

**Concurrency Safety:** The lock release cleanup (task #3) is correct. The TaskEngine's `_release_lock()` is called within the `self._lock` threading lock context in `complete_task`, `fail_task`, and `update_status`. The removal of the redundant `lock_manager.release_lock()` calls from `_run_dispatch_background.finally` and `cancel_task` is safe because:

- `cancel_task` calls `task_engine.cancel_task()` which calls `update_status(CANCELLED)` which calls `_release_lock()`.
- `_run_dispatch_background` calls `complete_task()` or `fail_task()`, both of which call `_release_lock()`.
- The `CancelledError` path is safe because `cancel_task` already released the lock before cancelling the asyncio task.

**Race Condition Handling:** The `test_cancel_complete_race_no_crash` test validates the critical race between cancel and completion. The `InvalidTransitionError` catch in `_run_dispatch_background` prevents crashes when a task is cancelled while the background coroutine is completing.

### 2. Intent & Correctness

**Task #2 (Description Quote Fix):**

- `list_agents()` at line 313 now wraps the description value with `_strip_quotes()`, matching the behavior of `_parse_agent_metadata()` used by the resource system.
- The new `test_descriptions_consistent_with_resources` test at line 666-694 directly verifies that `list_agents` descriptions and resource descriptions are identical for the same agent.
- This fix aligns with the ADR requirement that both discovery mechanisms (list_agents tool and MCP resources) present consistent metadata.

**Task #3 (Redundant Lock Release Cleanup):**

- Lock release responsibility is now solely in the TaskEngine layer (`_release_lock()` called on terminal transitions).
- The MCP layer (mcp_dispatch.py) no longer performs explicit lock releases, eliminating double-release scenarios.
- The `cancel_task` tool still cancels the asyncio background task after the engine state transition, which is the correct ordering.

**Task #4 (New Test Coverage):**

- `TestHelpers`: Unit tests for `_strip_quotes` and `_parse_tools` cover edge cases (empty string, single char, whitespace-only).
- `test_summary_truncation`: Validates the 500-char summary limit from the ADR result schema.
- `test_empty_task_string_dispatches`: Edge case coverage for empty task content.
- `test_descriptions_consistent_with_resources`: Cross-validates the bug fix from task #2.
- `test_delete_task_does_not_release_lock`: Important negative test proving `delete_task` is a hard removal that does not trigger lock lifecycle hooks.
- `test_input_required_to_failed_releases_lock` and `test_input_required_to_cancelled_releases_lock`: Cover the input_required -> terminal state transition paths for lock release.

### 3. Architectural Compliance

- The 5-state lifecycle (working, input_required, completed, failed, cancelled) is correctly implemented per ADR dispatch-task-contract Decision 1.
- Lock release on terminal transitions aligns with ADR dispatch-workspace-safety Decision 1 ("Locks are released when the task transitions to a terminal state").
- The structured result schema (taskId, status, agent, model_used, duration_seconds, summary, response, artifacts) matches ADR dispatch-task-contract Decision 2.
- Permission mode resolution priority (per-dispatch > agent frontmatter > read-write default) matches ADR dispatch-task-contract Decision 3.

### 4. Protocol Correctness

- All MCP tool return types remain `str` (JSON-serialized), consistent with `structured_output=False`.
- Tool signatures unchanged: `list_agents()`, `dispatch_agent(agent, task, model?, mode?)`, `get_task_status(task_id)`, `cancel_task(task_id)`, `get_locks()`.
- JSON response schemas are preserved across all tools.

### 5. Test Results

```
146 passed in 6.20s
```

- `test_mcp_dispatch.py`: 65 tests passed
- `test_task_engine.py`: 81 tests passed

No failures, no warnings, no skipped tests.

### 6. Drift Detection

No unplanned features or logic were introduced. All changes map directly to the three task scopes (description quote fix, redundant lock release cleanup, new test coverage).

## Recommendations

1. Consider removing the bare `finally: pass` block in `_run_dispatch_background` (line 479-483). The comment is valuable documentation, but it could be placed as a regular comment above the function or at the end of the except blocks instead.

2. The `LockConflictError` exception class in `task_engine.py` (line 80-81) is defined but never raised anywhere in the codebase. It may be intended for future use, but if not, it should be tracked for cleanup.

## Notes

- The `task_engine.py` module was not modified by any of the three tasks. It was reviewed for correctness of the lock release integration.
- The `acp_dispatch.py` module was not in scope and was not reviewed.
- All changes are backward-compatible. No MCP protocol contracts were modified.

---
feature: dispatch
phase: phase4
step: 2
date: 2026-02-07
status: complete
related:
  - "[[2026-02-07-dispatch-phase4-plan]]"
  - "[[2026-02-07-dispatch-phase4-step1]]"
---

# Step 2: Implement Advisory File Lock Manager

## Changes

### `task_engine.py`

Added `FileLock` dataclass and `LockManager` class per ADR dispatch-workspace-safety Decision 1.

**FileLock dataclass:**

- `task_id: str` -- owning task UUID
- `paths: frozenset[str]` -- workspace-relative paths this task intends to write
- `mode: str` -- permission mode (read-write / read-only)
- `acquired_at: float` -- monotonic timestamp

**LockManager class:**

- `acquire_lock(task_id, paths, mode)` -- registers write intent, returns (lock, warnings). Conflicts are advisory: the lock is still acquired but warnings list path overlaps.
- `release_lock(task_id)` -- releases the lock, returns True if found.
- `check_conflicts(paths)` -- checks paths against all active locks.
- `get_lock(task_id)` -- returns the lock for a specific task.
- `get_locks()` -- returns all active locks.
- `validate_readonly_paths(paths)` -- static method, checks that all paths are within `.docs/` prefix.

**LockConflictError exception** -- available for callers needing explicit error raising.

**Design decisions:**

- Lock state is in-memory (dict-based), no filesystem lock files.
- Thread-safe via `threading.Lock`.
- `frozenset` for paths (immutable after acquisition).
- Conflicts are advisory: `acquire_lock` still succeeds but returns warning strings.
- `validate_readonly_paths` normalizes backslashes for Windows compatibility.
- `READONLY_ALLOWED_PREFIXES = (".docs/",)` as class constant for extensibility.

**Bug fixes applied:**

- Added `logging` import and module-level `logger` for consistent logging across the task engine.
- Fixed `check_conflicts()` message: changed `agent={existing.task_id}` (incorrect) to `mode={existing.mode}` (meaningful).

## Verification

- All 51 task engine tests pass (no regressions).
- All 45 dispatch tests pass (no regressions).
- Smoke test: acquire, conflict detection, release, readonly validation all correct.

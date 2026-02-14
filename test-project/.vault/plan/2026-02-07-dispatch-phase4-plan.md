---
feature: dispatch
phase: phase4
date: 2026-02-07
related:
  - [[2026-02-07-dispatch-architecture.md]]
  - [[2026-02-07-dispatch-workspace-safety.md]]
  - [[2026-02-07-dispatch-task-contract.md]]
  - [[2026-02-07-dispatch-phase3-plan.md]]
---

# Phase 4: Advisory Locking and Permission Enforcement

## Goal

Implement advisory file locking for shared workspace coordination and enforce permission modes (read-write / read-only) at the dispatch layer. This is the final phase of the MCP dispatch server architecture.

## Prerequisites

- Phase 3 complete: agent resources, file-watching, standardized frontmatter with `mode` field
- Task engine with 5-state lifecycle (Phase 2)
- `mode` parameter accepted on `dispatch_agent` but currently advisory (not enforced)

## Steps

### Step 1: Research permission enforcement strategies

**Complexity:** LOW
**Output:** Understanding of how to enforce read-only mode at the ACP dispatch layer

Research:

- How `run_dispatch()` passes context to sub-agents (system prompt injection)
- Whether ACP supports permission constraints on the protocol level
- How to pass `mode` context so sub-agents respect file restrictions
- Practical enforcement: system prompt instruction vs process-level sandboxing
- Review how agent `mode` frontmatter defaults interact with per-dispatch overrides

Per ADR dispatch-task-contract Decision 3: enforcement passes permission context via the ACP transport layer to the sub-agent's system prompt. True OS-level sandboxing is out of scope.

### Step 2: Implement advisory file lock manager

**Complexity:** HIGH
**Files:**

- `.rules/scripts/task_engine.py` (extend)

Add advisory locking to the task engine per ADR dispatch-workspace-safety Decision 1:

**Lock semantics:**

- When a task is created with `mode: "read-only"`, register advisory locks on `.docs/` (write-allowed zone)
- When a task is created with `mode: "read-write"`, no path restrictions
- Track which paths each active task intends to write to
- Detect conflicts when two tasks target the same paths
- Release locks when task transitions to terminal state (completed, failed, cancelled)

**Lock data model:**

```python
@dataclass
class FileLock:
    task_id: str
    paths: set[str]       # Paths this task intends to write
    mode: str             # read-write | read-only
    acquired_at: float
```

**Lock manager methods:**

- `acquire_lock(task_id, paths, mode)` — register write intent
- `release_lock(task_id)` — release on task completion
- `check_conflicts(paths)` — check if paths conflict with active locks
- `get_locks()` — list all active locks

**Key constraints:**

- Lock state is in-memory (no filesystem lock files) per ADR
- Locks are advisory (logged warnings, not OS-enforced)
- Lock manager is part of `task_engine.py` (same standalone module)

### Step 3: Enforce permission mode in dispatch_agent

**Complexity:** MEDIUM
**Files:**

- `.rules/scripts/mcp_dispatch.py`

Upgrade `dispatch_agent` to enforce permission modes:

1. **Resolve effective mode:** If `mode` not specified on dispatch, use agent's frontmatter `default_mode`. Fall back to `"read-write"`.
2. **Inject mode into sub-agent system prompt:** Prepend permission instructions to the task content:
   - `read-only`: "You MUST only write files within the `.docs/` directory. Do not modify any source code files."
   - `read-write`: No restriction injected.
3. **Register advisory lock:** Call lock manager with task_id and mode.
4. **Log mode in task metadata:** Store effective mode in task engine for auditing.

### Step 4: Add lock-aware MCP tools

**Complexity:** MEDIUM
**Files:**

- `.rules/scripts/mcp_dispatch.py`

Add lock visibility tools:

**`get_locks` tool:**

- Returns all active advisory locks (task_id, paths, mode, acquired_at)
- Enables team leads to see which tasks are holding locks

**Update `get_task_status`:**

- Include lock information in task status response
- Show which paths the task is locking

### Step 5: Integrate lock release with task lifecycle

**Complexity:** MEDIUM
**Files:**

- `.rules/scripts/task_engine.py`
- `.rules/scripts/mcp_dispatch.py`

Ensure locks are released on all terminal state transitions:

- `complete_task()` — release lock
- `fail_task()` — release lock
- `cancel_task()` — release lock
- TTL expiry — release lock

This must be atomic with the state transition to prevent lock leaks.

### Step 6: Write lock manager tests

**Complexity:** MEDIUM
**Files:**

- `.rules/scripts/tests/test_task_engine.py` (extend)

Test coverage:

- Lock acquisition and release
- Conflict detection between concurrent tasks
- Lock release on task completion/failure/cancellation
- Read-only mode restricts to `.docs/` paths
- Read-write mode has no restrictions
- Lock state after TTL expiry
- No lock leaks after terminal transitions

### Step 7: Write permission enforcement integration tests

**Complexity:** MEDIUM
**Files:**

- `.rules/scripts/tests/test_mcp_dispatch.py` (extend)

Test coverage:

- `dispatch_agent` with `mode: "read-only"` injects permission prompt
- `dispatch_agent` with `mode: "read-write"` does not inject restrictions
- Default mode from agent frontmatter is used when not specified
- `get_locks` returns active locks
- Lock released after task completes
- Conflict detection logged on overlapping dispatches

## ADR Compliance Checklist

- [ ] Advisory file locking managed by task engine (ADR: dispatch-workspace-safety, Decision 1)
- [ ] Lock state in-memory, no filesystem lock files (ADR: dispatch-workspace-safety, Decision 1)
- [ ] Locks released on terminal state transitions (ADR: dispatch-workspace-safety, Decision 1)
- [ ] read-only mode restricts writes to `.docs/` (ADR: dispatch-task-contract, Decision 3)
- [ ] read-write mode permits full workspace access (ADR: dispatch-task-contract, Decision 3)
- [ ] Permission context passed via ACP transport to sub-agent system prompt (ADR: dispatch-task-contract, Decision 3)
- [ ] Agent frontmatter `mode` used as default (ADR: dispatch-task-contract, Decision 3)
- [ ] `acp_dispatch.py` preserved as library (ADR: dispatch-architecture, Decision 4)
- [ ] Task engine remains standalone module (ADR: dispatch-protocol-selection, Decision 1)

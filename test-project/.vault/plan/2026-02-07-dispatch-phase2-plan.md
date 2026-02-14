---
feature: dispatch
phase: phase2
date: 2026-02-07
related:
  - [[2026-02-07-dispatch-architecture.md]]
  - [[2026-02-07-dispatch-task-contract.md]]
  - [[2026-02-07-dispatch-protocol-selection.md]]
  - [[2026-02-07-dispatch-phase1-plan.md]]
---

# Phase 2: Async MCP Tasks and Internal Task Engine

## Goal

Upgrade the Phase 1 synchronous MCP dispatch server to support async dispatch via the MCP Tasks primitive. `dispatch_agent` returns immediately with a `taskId` and `status: "working"`. Team leads poll via `get_task_status` or receive results asynchronously. An internal task engine manages the 5-state lifecycle.

## Prerequisites

- Phase 1 complete: `mcp_dispatch.py` with synchronous `dispatch_agent` and `list_agents`
- `acp_dispatch.py` refactored as importable library with `run_dispatch()` returning response text

## Steps

### Step 1: Research MCP Tasks primitive API

**Complexity:** LOW
**Output:** Understanding of MCP Tasks spec and FastMCP SDK support

Research:

- MCP Tasks primitive specification (2025-11-25 experimental)
- How FastMCP handles task-augmented `tools/call` responses
- `tasks/get` and `tasks/result` protocol methods
- Whether FastMCP has built-in Tasks support or if we need raw JSON-RPC handling
- How `taskId` is generated and returned to the client

Consult MCP SDK source and documentation. Do NOT write code.

### Step 2: Implement internal task engine

**Complexity:** HIGH
**Files:**

- Create `.rules/scripts/task_engine.py`

Implement the 5-state task engine per ADR dispatch-task-contract Decision 1:

```
States: working, input_required, completed, failed, cancelled
```

Task engine responsibilities:

- Generate and track task IDs (UUID)
- Store task state, metadata, and results in memory
- State transition validation (e.g., `completed` is terminal)
- Thread-safe access for concurrent tasks
- Task cleanup/expiry for long-running server

Task data model:

```python
@dataclass
class DispatchTask:
    task_id: str           # UUID
    agent: str             # Agent name
    status: str            # working | input_required | completed | failed | cancelled
    created_at: float      # time.monotonic()
    model: str | None
    mode: str              # read-write | read-only
    result: dict | None    # Structured result on completion
    error: str | None      # Error message on failure
```

The task engine is a standalone module with no MCP or ACP dependencies.

### Step 3: Add `get_task_status` and `cancel_task` MCP tools

**Complexity:** MEDIUM
**Files:**

- `.rules/scripts/mcp_dispatch.py`

Add two new tools:

**`get_task_status`:**

- Input: `task_id` (string, required)
- Returns current task state, metadata, and result (if completed)
- Returns error if task_id not found

**`cancel_task`:**

- Input: `task_id` (string, required)
- Transitions task to `cancelled` state
- Attempts to terminate the sub-agent process if still running
- Returns confirmation or error

### Step 4: Convert `dispatch_agent` to async dispatch

**Complexity:** HIGH
**Files:**

- `.rules/scripts/mcp_dispatch.py`

Refactor `dispatch_agent` to:

1. Create a task via the task engine (status: `working`)
2. Spawn `run_dispatch()` as a background asyncio task
3. Return immediately with `{ taskId, status: "working" }`
4. When `run_dispatch()` completes, update task engine with result
5. On error, update task engine with `failed` status

Key considerations:

- `run_dispatch()` is async — wrap in `asyncio.create_task()`
- Capture result/error in a callback that updates the task engine
- Handle process cleanup if task is cancelled mid-flight
- The structured result schema from ADR (taskId, status, agent, artifacts, summary, duration_seconds, model_used)

### Step 5: Harden Phase 1 test gaps

**Complexity:** MEDIUM
**Files:**

- `.rules/scripts/tests/test_mcp_dispatch.py`

Address the 6 coverage gaps identified by the Phase 1 reviewer:

1. Test successful dispatch (mock `run_dispatch` returning successfully)
2. Test `DispatchError` path
3. Test generic `Exception` catch-all
4. Test path traversal rejection (`../../etc/passwd` as task path)
5. Test `quiet=True` propagation
6. Reduce brittleness of `_tool_manager._tools` access

### Step 6: Write task engine tests

**Complexity:** MEDIUM
**Files:**

- Create `.rules/scripts/tests/test_task_engine.py`

Test coverage:

- Task creation and ID generation
- State transitions (working → completed, working → failed, working → cancelled)
- Invalid state transitions rejected (completed → working)
- Concurrent task tracking
- Task lookup by ID
- Task expiry/cleanup

### Step 7: Write async dispatch integration tests

**Complexity:** MEDIUM
**Files:**

- `.rules/scripts/tests/test_mcp_dispatch.py` (extend)

Test coverage:

- `dispatch_agent` returns immediately with taskId
- `get_task_status` returns current state
- Task transitions to `completed` after background dispatch finishes
- `cancel_task` transitions to `cancelled`
- Multiple concurrent tasks tracked independently
- Unknown task_id returns error

## ADR Compliance Checklist

- [ ] 5-state machine: working, input_required, completed, failed, cancelled (ADR: dispatch-task-contract, Decision 1)
- [ ] Structured result schema with taskId, status, agent, artifacts, summary, duration_seconds, model_used (ADR: dispatch-task-contract, Decision 2)
- [ ] `get_task_status` and `cancel_task` tools added (ADR: dispatch-architecture, Decision 2)
- [ ] Async dispatch via MCP Tasks primitive (ADR: dispatch-architecture, Decision 3, Phase 2)
- [ ] Task engine is internal, not exposed as a protocol (ADR: dispatch-protocol-selection, Decision 1)
- [ ] `acp_dispatch.py` preserved as library (ADR: dispatch-architecture, Decision 4)
- [ ] Python implementation (ADR: dispatch-project-scope, Decision 3)

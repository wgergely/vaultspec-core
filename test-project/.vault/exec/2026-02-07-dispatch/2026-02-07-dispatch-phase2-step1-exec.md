---
tags:
  - "#exec"
  - "#uncategorized"
date: 2026-02-07
---
# Step 1: Research MCP Tasks Primitive API and FastMCP Support

## Summary

Deep research of the MCP SDK v1.26.0 experimental Tasks system. Findings confirm the SDK provides a complete, production-ready task infrastructure that our Phase 2 plan can leverage directly.

## Key Findings

### 1. MCP Tasks is fully implemented in SDK v1.26.0 (experimental)

The `mcp` Python SDK v1.26.0 ships with comprehensive experimental task support under `mcp.shared.experimental.tasks` and `mcp.server.experimental`. The implementation is labeled "experimental" (API may change) but is fully functional.

### 2. Five-State Machine Matches Our ADR

The SDK defines these states in `mcp.types`:

```python
TaskStatus = Literal["working", "input_required", "completed", "failed", "cancelled"]
```

With constants: `TASK_STATUS_WORKING`, `TASK_STATUS_INPUT_REQUIRED`, `TASK_STATUS_COMPLETED`, `TASK_STATUS_FAILED`, `TASK_STATUS_CANCELLED`.

Terminal states: `completed`, `failed`, `cancelled` -- transitions FROM terminal states are rejected.

This is an exact match for our ADR decision (dispatch-task-contract, Decision 1).

### 3. SDK Provides Complete Task Infrastructure

| Component | Location | Purpose |
|-----------|----------|---------|
| `TaskStore` (abstract) | `mcp.shared.experimental.tasks.store` | Storage interface for tasks |
| `InMemoryTaskStore` | `mcp.shared.experimental.tasks.in_memory_task_store` | In-memory implementation with TTL/expiry |
| `TaskContext` | `mcp.shared.experimental.tasks.context` | Pure state management (no server deps) |
| `ServerTaskContext` | `mcp.server.experimental.task_context` | Server-integrated with elicit/sample |
| `TaskSupport` | `mcp.server.experimental.task_support` | Configuration object (store + queue + handler) |
| `TaskResultHandler` | `mcp.server.experimental.task_result_handler` | Handles `tasks/result` with dequeue-send-wait |
| `ExperimentalHandlers` | `mcp.server.lowlevel.experimental` | Auto-registers `tasks/get`, `tasks/result`, `tasks/list`, `tasks/cancel` |
| Helper functions | `mcp.shared.experimental.tasks.helpers` | `is_terminal()`, `cancel_task()`, `create_task_state()`, `task_execution()` |

### 4. Enabling Tasks on the Low-Level Server

```python
# One-line enablement with defaults:
server.experimental.enable_tasks()

# Custom store/queue:
server.experimental.enable_tasks(
    store=MyCustomTaskStore(),
    queue=MyCustomMessageQueue(),
)
```

This auto-registers default handlers for:

- `tasks/get` -- returns task status
- `tasks/result` -- waits for completion, returns result
- `tasks/list` -- paginated task listing
- `tasks/cancel` -- cancels non-terminal tasks

### 5. FastMCP Does NOT Have High-Level Task Wrappers

FastMCP (`mcp.server.fastmcp.FastMCP`) wraps the low-level `MCPServer` (accessible via `._mcp_server`). It does NOT expose task-specific decorators or helpers. To use tasks with FastMCP, we access the low-level server:

```python
mcp = FastMCP("pp-dispatch")
mcp._mcp_server.experimental.enable_tasks()
```

### 6. Task-Augmented Tool Calls

When a client sends a `tools/call` request with a `task` field in `_meta`:

```json
{
  "method": "tools/call",
  "params": {
    "name": "dispatch_agent",
    "arguments": {"agent": "adr-researcher", "task": "..."},
    "_meta": {
      "task": {"ttl": 600000}
    }
  }
}
```

The server detects `task_metadata` from request params and populates `ctx.experimental.is_task`. The tool handler can then call `ctx.experimental.run_task(work_fn)` to:

1. Create a task in the store (status: `working`)
2. Spawn `work_fn` in a background task group
3. Return `CreateTaskResult` immediately with the task ID

### 7. The `Experimental.run_task()` Pattern

```python
async def run_task(
    self,
    work: Callable[[ServerTaskContext], Awaitable[Result]],
    *,
    task_id: str | None = None,
    model_immediate_response: str | None = None,
) -> CreateTaskResult:
```

The work function receives a `ServerTaskContext` with:

- `update_status()` for progress updates
- `complete()` / `fail()` for terminal transitions
- `elicit()` for user input requests
- `create_message()` for sampling

If the work function returns a `Result`, the task is auto-completed. If it raises, the task is auto-failed.

### 8. Task Data Model (`mcp.types.Task`)

```python
class Task(BaseModel):
    taskId: str
    status: TaskStatus  # working | input_required | completed | failed | cancelled
    statusMessage: str | None = None
    createdAt: datetime
    lastUpdatedAt: datetime
    ttl: int | None      # retention in ms
    pollInterval: int | None = None  # suggested poll interval in ms
```

### 9. InMemoryTaskStore Features

- UUID-based task ID generation
- Lazy TTL expiration (cleanup on access)
- `anyio.Event`-based wait/notify for `wait_for_update()`
- Pagination support for `list_tasks()`
- Thread-safe for single-process async use

## Implications for Phase 2

### Decision: Use SDK's InMemoryTaskStore Instead of Custom task_engine.py

The SDK's `InMemoryTaskStore` provides exactly what our plan specified for `task_engine.py`:

- UUID task IDs
- 5-state machine with transition validation
- TTL-based expiry
- Thread-safe async access

**However**, the plan requires `task_engine.py` as a standalone module with no MCP dependencies. The SDK's task store IS that module (it has no MCP server dependencies -- only `anyio` and `mcp.types`).

**Recommendation:** Instead of building a custom `task_engine.py` from scratch, we should build a thin wrapper (`task_engine.py`) that:

1. Re-exports the SDK's `InMemoryTaskStore` as the storage backend
2. Adds our dispatch-specific metadata (agent, model, mode, duration)
3. Provides a `DispatchTask` dataclass with our schema
4. Maps between our structured result format and the SDK's `Result` type

This approach:

- Leverages battle-tested SDK code for state machine and storage
- Keeps `task_engine.py` focused on dispatch-specific concerns
- Maintains the "no MCP/ACP deps" intent -- `task_engine.py` imports from `mcp.types` and `mcp.shared.experimental.tasks` (pure data types, no server dependencies)
- Reduces implementation risk and testing burden

### Integration Pattern for `dispatch_agent`

The tool handler needs to:

1. Access `mcp._mcp_server.request_context.experimental`
2. Check `experimental.is_task` to determine sync vs async mode
3. If task-augmented: use `experimental.run_task()` to spawn background work
4. If not task-augmented: fall back to synchronous behavior (Phase 1 compat)

### Custom `get_task_status` and `cancel_task` Tools

The SDK auto-registers protocol-level `tasks/get` and `tasks/cancel` handlers. Our MCP tools (`get_task_status`, `cancel_task`) are higher-level wrappers that:

- Add dispatch-specific metadata to responses (agent name, model, etc.)
- Provide human-readable summaries
- Can terminate sub-agent processes on cancel (SDK only updates state)

These should use the same `InMemoryTaskStore` instance as the SDK's task support.

## Files Examined

- `C:\Users\hello\miniconda3\Lib\site-packages\mcp\types.py` (Task, TaskStatus, CreateTaskResult)
- `C:\Users\hello\miniconda3\Lib\site-packages\mcp\shared\experimental\tasks\store.py` (TaskStore ABC)
- `C:\Users\hello\miniconda3\Lib\site-packages\mcp\shared\experimental\tasks\in_memory_task_store.py` (InMemoryTaskStore)
- `C:\Users\hello\miniconda3\Lib\site-packages\mcp\shared\experimental\tasks\helpers.py` (is_terminal, cancel_task, task_execution)
- `C:\Users\hello\miniconda3\Lib\site-packages\mcp\shared\experimental\tasks\context.py` (TaskContext)
- `C:\Users\hello\miniconda3\Lib\site-packages\mcp\server\experimental\task_support.py` (TaskSupport)
- `C:\Users\hello\miniconda3\Lib\site-packages\mcp\server\experimental\task_context.py` (ServerTaskContext)
- `C:\Users\hello\miniconda3\Lib\site-packages\mcp\server\experimental\request_context.py` (Experimental.run_task)
- `C:\Users\hello\miniconda3\Lib\site-packages\mcp\server\lowlevel\experimental.py` (ExperimentalHandlers.enable_tasks)
- `C:\Users\hello\miniconda3\Lib\site-packages\mcp\server\lowlevel\server.py` (task_metadata extraction)
- `C:\Users\hello\miniconda3\Lib\site-packages\mcp\server\fastmcp\server.py` (FastMCP._mcp_server)

---
feature: dispatch
phase: phase4
step: 1
date: 2026-02-07
status: complete
related:
  - "[[2026-02-07-dispatch-phase4-plan]]"
---

# Step 1: Research Permission Enforcement Strategies

## Findings

### How run_dispatch() Passes Context to Sub-Agents

1. `run_dispatch(agent_name, initial_task, model_override, ...)` does NOT accept a `mode` parameter.
2. Provider `prepare_process()` builds `system_prompt = construct_system_prompt(persona, rules)` from agent persona and loaded rules. No permission context is injected.
3. `initial_task` is passed as `task_context` to `prepare_process()` and used as the `start_prompt` in the ACP interactive loop (line 632 of `acp_dispatch.py`).
4. The Gemini provider writes system prompt to a temp file and passes via `GEMINI_SYSTEM_MD` env var. The Claude provider uses `construct_system_prompt()` similarly.

### ACP Protocol-Level Permission Constraints

ACP does not support permission constraints at the protocol level. The spawned sub-agent process runs with full filesystem access. OS-level sandboxing is out of scope per ADR dispatch-workspace-safety.

### Best Injection Point for Permission Context

**Decision: Prepend mode instructions to `task_content` in `_run_dispatch_background()`.**

This approach:

- Does NOT modify `acp_dispatch.py` library interface (preserves ADR dispatch-architecture Decision 4)
- Injects permission instructions into the sub-agent's initial prompt, which is the first thing the agent sees
- Is simple, testable, and consistent with the plan's Step 3 guidance

For `read-only` mode, prepend:

```
PERMISSION MODE: READ-ONLY
You MUST only write files within the `.docs/` directory. Do not modify any source code files.
```

For `read-write` mode, no restriction injected.

### Agent Frontmatter `mode` Defaults

- `_parse_agent_metadata()` reads `mode` from frontmatter into `_agent_cache[name]["default_mode"]`
- In `dispatch_agent()`, resolve effective mode: if `mode` not specified by caller, look up `_agent_cache[agent]["default_mode"]`, fall back to `"read-write"`
- Currently `dispatch_agent` has `mode: str = "read-write"` as a default parameter; this needs refinement to support agent-default resolution

### Lock Manager Integration Points

- `task_engine.py` already stores `mode` on each `DispatchTask` dataclass
- Lock manager will be a new class in `task_engine.py` alongside `TaskEngine`
- Lock acquisition in `dispatch_agent()` after task creation
- Lock release integrated with `complete_task()`, `fail_task()`, `cancel_task()`, and TTL expiry
- Lock state is in-memory (dict-based), no filesystem lock files

## Impact on Subsequent Steps

- Step 2: `FileLockManager` class in `task_engine.py` with `acquire_lock`, `release_lock`, `check_conflicts`, `get_locks`
- Step 3: `dispatch_agent()` resolves effective mode, injects permission prompt, registers advisory lock
- Step 5: Terminal state transitions in `TaskEngine` call `lock_manager.release_lock(task_id)` atomically

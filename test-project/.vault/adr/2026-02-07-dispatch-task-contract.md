---
feature: dispatch
date: 2026-02-07
related:
  - [[2026-02-07-dispatch-project-scope.md]]
  - [[2026-02-07-dispatch-protocol-selection.md]]
  - [[2026-02-07-dispatch-architecture.md]]
  - [[2026-02-07-dispatch-workspace-safety.md]]
---

# Dispatch Framework: Task Result Contract

## Context

The current dispatcher has no formal task lifecycle. A sub-agent is spawned, its stdout is captured, and the calling agent interprets the result as unstructured text. There is no concept of task state, progress tracking, structured results, or failure semantics.

The protocol research identified two competing task state models:

1. **A2A Task States** (9 states): `submitted`, `working`, `input_required`, `auth_required`, `completed`, `failed`, `canceled`, `rejected`, `unknown`.
2. **MCP Tasks States** (5 states): `working`, `input_required`, `completed`, `failed`, `cancelled`.

Since the dispatch interface is MCP (Layer 1), the task state model should align with MCP's native primitives to avoid protocol translation overhead.

## Decisions

### 1. Adopt MCP Tasks State Machine

**Decision:** The internal task engine uses the MCP Tasks 5-state machine:

```
                    +--> completed
                    |
working --+--> input_required --+--> working (resumed)
                    |
                    +--> failed
                    |
                    +--> cancelled
```

**States:**

- **`working`**: Sub-agent is actively processing the task.
- **`input_required`**: Sub-agent needs additional input from the team lead (e.g., clarification, approval).
- **`completed`**: Task finished successfully with structured results.
- **`failed`**: Task terminated with an error.
- **`cancelled`**: Task was explicitly cancelled by the team lead.

**Rationale:**

- MCP Tasks states map directly to the dispatch interface protocol, requiring no translation layer.
- The 5-state model covers all practical dispatch scenarios without the overhead of A2A's additional states (`submitted`, `auth_required`, `rejected`, `unknown`).
- `submitted` is unnecessary because MCP tool calls are synchronous at invocation -- the task transitions directly to `working`.
- `auth_required` and `rejected` are not applicable to local subprocess dispatch.
- `unknown` is an error state that can be represented as `failed` with appropriate error metadata.

### 2. Structured Task Result Schema

**Decision:** Completed tasks return a structured result object, not raw stdout text.

**Result Schema:**

```json
{
  "taskId": "uuid",
  "status": "completed",
  "agent": "adr-researcher",
  "artifacts": [
    {
      "type": "file",
      "path": ".docs/adr/2026-02-07-example-adr.md",
      "description": "Architecture Decision Record"
    }
  ],
  "summary": "Created ADR documenting the dispatch protocol selection.",
  "duration_seconds": 45,
  "model_used": "gemini-3-pro-preview"
}
```

**Rationale:**

- Structured results enable the team lead to programmatically process outcomes (e.g., read generated files, chain to subsequent tasks).
- The `artifacts` array captures what the sub-agent produced, replacing the convention of "sub-agents write files and hope the caller knows where."
- `summary` provides a human-readable description for the team lead's context.

### 3. Implement READ-WRITE and READ-ONLY Permission Modes

**Decision:** Sub-agents operate in one of two permission modes:

| Mode         | File Access                        | Use Case                        |
|--------------|------------------------------------|---------------------------------|
| `read-write` | Full workspace access (default)    | Execution agents, code changes  |
| `read-only`  | Write only to `.docs/` directory   | Research, ADR, reference agents |

**Rationale:**

- Most sub-agents in the current workflow (adr-researcher, task-writer, reference-auditor, docs-curator) produce only `.docs/` artifacts. Restricting their write scope prevents accidental code modifications.
- Execution agents (simple-executor, standard-executor, complex-executor) require full workspace access to implement code changes.
- Two modes provide meaningful safety without the complexity of fine-grained per-directory ACLs.

**Implications:**

- Permission mode is specified per-dispatch via the `mode` parameter on `dispatch_agent`.
- Agent definitions in `.rules/agents/*.md` may declare a default mode in their frontmatter.
- Enforcement is advisory in Phase 1-3 (logged but not blocked), mandatory in Phase 4.
- The ACP transport layer passes permission context to the sub-agent's system prompt.

### 4. Rejected Alternative: Full A2A 9-State Machine

**Decision:** The A2A 9-state task machine is not adopted.

**Rationale:**

- Four of the nine states (`submitted`, `auth_required`, `rejected`, `unknown`) have no meaningful mapping in local subprocess dispatch.
- Using A2A states would require a translation layer between the MCP interface (Layer 1) and the internal engine (Layer 2), adding complexity without functional benefit.
- If A2A transport is ever added (e.g., for remote agent dispatch), the 5-state model can be mapped to A2A's 9-state model at that boundary.

## Status

Accepted

## Consequences

**Benefits:**

- MCP-native state model eliminates protocol translation between the dispatch interface and the task engine.
- Structured results replace unstructured stdout capture, enabling programmatic task chaining.
- Two permission modes provide practical safety for the most common dispatch patterns.
- The 5-state model is simple enough to implement correctly and reason about.

**Drawbacks:**

- Structured results require sub-agents to report their artifacts, which may need system prompt engineering.
- Permission enforcement at the ACP layer is advisory (the sub-agent process has full filesystem access); true enforcement would require sandboxing.
- The simplified state model may need extension if remote dispatch (non-subprocess) scenarios emerge.

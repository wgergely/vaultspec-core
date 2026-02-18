---
tags:
  - "#adr"
  - "#uncategorized"
date: 2026-02-07
related:
  - "[[2026-02-07-dispatch-project-scope.md]]"
  - "[[2026-02-07-dispatch-protocol-selection.md]]"
  - "[[2026-02-07-dispatch-task-contract.md]]"
  - "[[2026-02-07-dispatch-workspace-safety.md]]"
---
# Dispatch Framework: MCP Server Architecture

## Context

The protocol selection ADR established a three-layer stack: MCP (dispatch interface) -> Task Engine (internal) -> ACP (sub-agent transport). This ADR defines the concrete architecture of the MCP dispatch server, its relationship to the existing codebase, and the implementation phasing strategy.

The current dispatcher (`acp_dispatch.py`, 858 lines) is a monolithic script that:

1. Parses CLI arguments for agent name, task description, and model override.
2. Loads agent frontmatter from `.rules/agents/*.md`.
3. Constructs provider-specific process specs via `agent_providers/`.
4. Spawns a sub-agent subprocess and runs an interactive ACP session.
5. Captures stdout and returns results as text.

This must be refactored into a long-lived MCP server that accepts typed JSON tool calls, manages concurrent task state, and integrates with the existing provider system.

## Decisions

### 1. Python MCP Server Using the Official `mcp` SDK

**Decision:** The dispatch server is a Python MCP server using Anthropic's official `mcp` SDK, communicating over stdio transport.

**Rationale:**

- The `mcp` Python SDK is the official, most mature implementation.
- The existing dispatch code (2,200+ lines of Python) carries forward with refactoring rather than rewriting.
- stdio transport is the standard for local MCP servers invoked via `.mcp.json`.

**Server Entry Point:**

```
.rules/scripts/mcp_dispatch.py   <- New MCP server (refactored from acp_dispatch.py)
.rules/scripts/acp_dispatch.py   <- Preserved as ACP client library (Layer 3)
.rules/scripts/agent_providers/  <- Unchanged provider system
```

**MCP Configuration (`.mcp.json`):**

```json
{
  "mcpServers": {
    "pp-dispatch": {
      "command": "python",
      "args": [".rules/scripts/mcp_dispatch.py"],
      "env": {}
    }
  }
}
```

### 2. Exposed MCP Tools

**Decision:** The server exposes the following tools:

| Tool               | Description                                  | MCP Tasks |
|---------------------|----------------------------------------------|-----------|
| `dispatch_agent`    | Dispatch a sub-agent with a task             | Required  |
| `get_task_status`   | Query the status of a dispatched task        | N/A       |
| `list_agents`       | List available agents and their capabilities | N/A       |
| `cancel_task`       | Cancel a running task                        | N/A       |

**`dispatch_agent` Schema:**

- `agent` (string, required): Agent name matching `.rules/agents/{name}.md`.
- `task` (string, required): Natural language task description or path to a plan document.
- `model` (string, optional): Model override (e.g., `gemini-3-pro-preview`).
- `mode` (string, optional): Permission mode -- `read-write` (default) or `read-only`.

**Rationale:**

- `dispatch_agent` with MCP Tasks support enables async dispatch: the tool returns immediately with a `taskId`, and the team lead polls via `get_task_status` or the MCP `tasks/get` primitive.
- `list_agents` enables dynamic agent discovery, replacing the current hard-coded knowledge of agent names.
- `cancel_task` provides graceful lifecycle management.

### 3. Incremental Implementation Phasing

**Decision:** The MCP server is built incrementally across four phases.

**Phase 1: Synchronous Dispatch (MVP)**

- MCP server with `dispatch_agent` tool (synchronous -- blocks until sub-agent completes).
- Wraps existing `run_dispatch()` logic from `acp_dispatch.py`.
- `list_agents` tool reads `.rules/agents/*.md` frontmatter.
- No task state machine yet -- results returned directly.
- **Goal:** Replace CLI invocation with typed MCP tool calls.

**Phase 2: Async Tasks**

- Implement MCP Tasks primitive on `dispatch_agent`.
- `dispatch_agent` returns immediately with `{ taskId, status: "working" }`.
- Internal task engine tracks state transitions.
- `get_task_status` and `tasks/get` return current state and results.
- **Goal:** Non-blocking dispatch enabling concurrent sub-agents.

**Phase 3: Agent Cards as MCP Resources**

- Server exposes agent definitions as MCP resources (`agents://{name}`).
- Resources are dynamically parsed from `.rules/agents/*.md` frontmatter at runtime.
- `resources/list` provides agent discovery with capability metadata.
- `list_changed` notification when agent files are modified.
- **Goal:** Machine-readable agent discovery via standard MCP resource protocol.

**Phase 4: Locking and Permissions**

- Advisory file locking for shared workspace coordination.
- `read-only` mode restricts sub-agent file operations to `.docs/` directory.
- `read-write` mode permits full workspace access (current behavior).
- Lock metadata tracked in task engine state.
- **Goal:** Safe concurrent multi-agent operation.

**Rationale:**

- Each phase delivers standalone value and can be validated independently.
- Phase 1 provides immediate improvement (typed invocation) with minimal risk.
- Later phases build on the foundation without requiring architectural changes.

### 4. Preserve `acp_dispatch.py` as ACP Client Library

**Decision:** The existing `acp_dispatch.py` is refactored into a library module, not deleted.

**Rationale:**

- The `GeminiDispatchClient`, `SessionLogger`, `_Terminal`, and `run_dispatch()` logic is correct at Layer 3 (ACP transport).
- The MCP server imports and calls these functions rather than reimplementing them.
- The CLI entry point (`if __name__ == "__main__"`) may be preserved for debugging and direct invocation.

**Implications:**

- `acp_dispatch.py` loses its role as the primary entry point but retains its role as the ACP session manager.
- The MCP server (`mcp_dispatch.py`) is the new primary entry point.

## Status

Accepted

## Consequences

**Benefits:**

- Typed JSON invocation eliminates shell string escaping and argument parsing errors.
- MCP Tasks enables non-blocking dispatch, allowing team leads to run multiple sub-agents concurrently.
- Incremental phasing minimizes risk and delivers value at each stage.
- Existing ACP client code is preserved, reducing implementation effort.
- `.mcp.json` provides auto-discovered, git-committable server registration.

**Drawbacks:**

- MCP Tasks is experimental and the API surface may change.
- A long-lived server process requires lifecycle management (startup, shutdown, error recovery).
- Phase 1 synchronous dispatch is a stepping stone that must be replaced by Phase 2 for production use.
- Two entry points (`mcp_dispatch.py` and `acp_dispatch.py`) may cause confusion during the transition period.

---

## Addendum: MCP Server Forwarding Design (2026-02-07)

**Context:** Decision 4 preserves `acp_dispatch.py` as the ACP client library, and the `session/new` call accepts an `mcp_servers` parameter for provisioning MCP servers to sub-agents. However, the current implementation passes `mcp_servers=[]`, meaning dispatched sub-agents have no access to MCP tools like `rust-mcp-server` (cargo build/test/clippy) or `pp-dispatch` (nested dispatch). This was identified as gap H3 in the Gemini A2A Alignment Report.

**Design:** The `session/new` `mcp_servers` parameter should be populated from the team lead's MCP configuration:

1. **Source:** Read MCP server definitions from `.gemini/settings.json` (key `mcpServers`) or `.mcp.json` at dispatch time.
2. **Filtering:** Not all team-lead MCP servers should be forwarded. A configurable allowlist (or denylist) determines which servers are passed to sub-agents. At minimum, `rust-mcp-server` (cargo tools) should be forwarded.
3. **Format conversion:** MCP server configs must be converted to the ACP `McpServerConfig` format expected by `session/new` (stdio command + args, or HTTP URL).
4. **Recursive dispatch guard:** The `pp-dispatch` server itself should generally NOT be forwarded to sub-agents to prevent infinite dispatch recursion, unless explicitly configured.

**Status:** Design documented. Implementation tracked as Phase 5B item 4 in the alignment report's recommended next steps.

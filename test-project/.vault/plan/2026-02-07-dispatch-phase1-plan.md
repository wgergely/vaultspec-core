---
feature: dispatch
phase: phase1
date: 2026-02-07
related:
  - [[2026-02-07-dispatch-architecture.md]]
  - [[2026-02-07-dispatch-protocol-selection.md]]
  - [[2026-02-07-dispatch-task-contract.md]]
  - [[2026-02-07-dispatch-workspace-safety.md]]
  - [[2026-02-07-dispatch-project-scope.md]]
---

# Phase 1: Synchronous MCP Dispatch Server (MVP)

## Goal

Replace the CLI-based `python acp_dispatch.py` invocation with a typed MCP server that exposes `dispatch_agent` and `list_agents` as MCP tools. Phase 1 is synchronous -- `dispatch_agent` blocks until the sub-agent completes.

## Prerequisites

- Python `mcp` SDK (official Anthropic package)
- Existing `acp_dispatch.py` preserved as ACP client library (Layer 3)
- Existing `agent_providers/` system unchanged

## Steps

### Step 1: Research MCP Python SDK patterns

**Complexity:** LOW
**Output:** Understanding of `mcp` SDK server patterns, stdio transport, tool registration

Research the official `mcp` Python SDK to understand:

- How to create an MCP server with stdio transport
- How to register tools with typed JSON schemas
- How tool handlers return results
- Error handling patterns
- Server lifecycle (startup, shutdown)

Consult the SDK documentation and examples. Do NOT write code yet.

### Step 2: Create MCP server skeleton

**Complexity:** MEDIUM
**Files:**

- Create `.rules/scripts/mcp_dispatch.py`

Implement:

- MCP server initialization with stdio transport
- Server metadata (name: `pp-dispatch`, version: `0.1.0`)
- Tool registration stubs for `dispatch_agent` and `list_agents`
- Proper `__main__` entry point
- Import path setup for `acp_dispatch` and `agent_providers`

The server must be runnable via `python .rules/scripts/mcp_dispatch.py` and respond to MCP `initialize` and `tools/list` requests.

### Step 3: Implement `list_agents` tool

**Complexity:** MEDIUM
**Files:**

- `.rules/scripts/mcp_dispatch.py`

Implement the `list_agents` tool handler:

- Reads `.rules/agents/*.md` files
- Parses frontmatter using existing `parse_frontmatter()` from `acp_dispatch.py`
- Returns structured JSON with agent name, tier, description for each agent
- Handles missing/malformed agent files gracefully

Tool schema:

```json
{
  "name": "list_agents",
  "description": "List available agents and their capabilities",
  "inputSchema": {
    "type": "object",
    "properties": {},
    "required": []
  }
}
```

### Step 4: Implement `dispatch_agent` tool (synchronous)

**Complexity:** HIGH
**Files:**

- `.rules/scripts/mcp_dispatch.py`
- `.rules/scripts/acp_dispatch.py` (minor refactoring to expose `run_dispatch()` as importable)

Implement the `dispatch_agent` tool handler:

- Accepts `agent` (required), `task` (required), `model` (optional), `mode` (optional)
- Loads agent definition via existing `load_agent()`
- Resolves provider via existing `get_provider_for_model()`
- Calls existing `run_dispatch()` synchronously (blocks until complete)
- Returns structured result with summary and any artifacts

Tool schema:

```json
{
  "name": "dispatch_agent",
  "description": "Dispatch a sub-agent to perform a task",
  "inputSchema": {
    "type": "object",
    "properties": {
      "agent": { "type": "string", "description": "Agent name from .rules/agents/" },
      "task": { "type": "string", "description": "Task description or path to plan document" },
      "model": { "type": "string", "description": "Model override (optional)" },
      "mode": { "type": "string", "enum": ["read-write", "read-only"], "default": "read-write" }
    },
    "required": ["agent", "task"]
  }
}
```

Key considerations:

- `acp_dispatch.py` currently uses `sys.exit()` on errors -- must be refactored to raise exceptions
- `run_dispatch()` uses `asyncio.run()` -- the MCP server also runs async, so need to handle event loop nesting
- The `_Terminal` class for stdout capture must work within MCP server context

### Step 5: Create `.mcp.json` configuration

**Complexity:** LOW
**Files:**

- Create `.mcp.json` in project root

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

### Step 6: Write tests

**Complexity:** MEDIUM
**Files:**

- Create `.rules/scripts/tests/test_mcp_dispatch.py`

Test coverage:

- Server initializes and responds to `tools/list`
- `list_agents` returns correct agent metadata
- `dispatch_agent` validates required parameters
- `dispatch_agent` handles missing agent gracefully
- Error responses have correct MCP error format

### Step 7: Update rules and documentation

**Complexity:** LOW
**Files:**

- `.rules/rules-custom/task-subagents.md` (update dispatch instructions)
- `.rules/rules/task-subagents.md` (sync)

Update the sub-agent dispatch rule to document MCP server usage alongside CLI fallback.

## ADR Compliance Checklist

- [ ] MCP server uses official `mcp` Python SDK (ADR: dispatch-architecture, Decision 1)
- [ ] stdio transport for local server communication (ADR: dispatch-architecture, Decision 1)
- [ ] `dispatch_agent` and `list_agents` tools exposed (ADR: dispatch-architecture, Decision 2)
- [ ] Existing `acp_dispatch.py` preserved as library, not deleted (ADR: dispatch-architecture, Decision 4)
- [ ] ACP remains the sub-agent transport layer (ADR: dispatch-protocol-selection, Decision 3)
- [ ] Python implementation language (ADR: dispatch-project-scope, Decision 3)
- [ ] Tool-agnostic via MCP standard (ADR: dispatch-project-scope, Decision 2)

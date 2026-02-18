---
tags:
  - "#adr"
  - "#uncategorized"
date: 2026-02-07
related:
  - "[[2026-02-07-dispatch-project-scope.md]]"
  - "[[2026-02-07-dispatch-architecture.md]]"
  - "[[2026-02-07-dispatch-task-contract.md]]"
  - "[[2026-02-07-dispatch-workspace-safety.md]]"
---
# Dispatch Framework: Protocol Selection

## Context

The multi-agent dispatch system operates across three distinct communication boundaries:

1. **Team Lead to Dispatcher** -- How a team lead agent (Claude Code or Gemini CLI) invokes the dispatch service.
2. **Internal Task Tracking** -- How the dispatcher manages task lifecycle and state transitions.
3. **Dispatcher to Sub-Agent** -- How the dispatcher spawns and communicates with sub-agent processes.

Three protocols were evaluated through deep research of official specifications and production implementations:

- **MCP (Model Context Protocol)** by Anthropic -- Agent-to-Tool/Service protocol over JSON-RPC 2.0/stdio. Has experimental Tasks primitive (2025-11-25 spec) for async durable operations.
- **ACP (Agent Client Protocol)** by Zed Industries -- Client-to-Agent protocol over JSON-RPC 2.0/stdio. Proxy Chains RFD for agent-to-agent (RFD status, not production).
- **A2A (Agent-to-Agent Protocol)** by Google/Linux Foundation -- Agent-to-Agent protocol over HTTPS/SSE. 9-state task machine. Requires HTTP transport (stdio transport is proposed but not merged).

Key findings from protocol research:

- The "Tool-as-Agent" pattern (expose agent dispatch as MCP tools) is validated by IBM, Microsoft, and LastMile AI in production.
- ACP proxy chains are RFD-stage with only a Rust reference implementation.
- A2A requires HTTP servers per agent -- inappropriate for local subprocess dispatch.
- Claude Code's internal multi-agent system (Task Tool, Agent Teams) is fully proprietary, not based on any open protocol.
- MCP Tasks primitive provides exactly the async dispatch pattern needed without HTTP overhead.

## Decisions

### 1. Adopt a Three-Layer Protocol Stack

**Decision:** The dispatch system uses three protocol layers, each at its correct boundary:

```
Layer 1: MCP          <- Team lead calls dispatcher (tool/service interface)
Layer 2: Task Engine  <- A2A-inspired state machine (internal)
Layer 3: ACP          <- Dispatcher spawns sub-agents (client-to-agent transport)
```

**Rationale:**

- **MCP at Layer 1** is protocol-correct: the dispatcher IS a service/tool that team leads consume. MCP is the established standard for this boundary, supported by Claude Code, Gemini, Cursor, and VS Code.
- **ACP at Layer 3** is protocol-correct: the dispatcher IS a client to sub-agents. ACP is specifically designed for client-to-agent communication over stdio/subprocess.
- **Internal Task Engine at Layer 2** bridges the semantic gap: MCP provides the interface, ACP provides the transport, but neither defines how tasks are tracked, how state transitions occur, or how results are structured. The task engine owns this logic.

**Implications:**

- No single protocol spans all three layers. Each layer uses the protocol designed for that boundary.
- The current architecture (CLI at Layer 1, ACP at Layer 3, no Layer 2) is replaced with protocol-aligned boundaries.
- The internal task engine is not exposed as a protocol -- it is implementation detail.

### 2. MCP is the Dispatch Interface (Layer 1)

**Decision:** Team leads invoke dispatch via MCP tool calls, replacing the current `python acp_dispatch.py` CLI invocation.

**Rationale:**

| Dimension      | CLI (current)           | MCP Server (adopted)                             |
|----------------|-------------------------|--------------------------------------------------|
| Invocation     | Shell string + escaping | Typed JSON schema                                |
| Async support  | Blocks Bash tool        | MCP Tasks returns immediately with taskId        |
| State          | Stateless per-call      | Long-lived server tracks active tasks            |
| Sharing        | Document CLI in rules   | `.mcp.json` in git, auto-discovered              |
| Cross-tool     | ACP-specific            | Any MCP client (Claude, Gemini, Cursor, VS Code) |
| Discovery      | Hard-coded              | Dynamic `tools/list` with `list_changed`         |

**Implications:**

- The MCP server exposes tools like `dispatch_agent`, `get_task_status`, `list_agents`.
- Both Claude Code and Gemini CLI connect to the same MCP server via `.mcp.json`.
- The CLI entry point (`acp_dispatch.py`) is refactored into an MCP server module.

### 3. ACP Remains the Sub-Agent Transport (Layer 3)

**Decision:** The dispatcher continues to use ACP for spawning and communicating with sub-agent processes.

**Rationale:**

- ACP is specifically designed for client-to-agent communication over stdio/subprocess -- exactly the dispatcher's relationship to sub-agents.
- The existing `GeminiDispatchClient` (ACP client) and provider system work correctly at this layer.
- ACP proxy chains (the official agent-to-agent mechanism) are RFD-stage and would add complexity without benefit over the MCP+ACP layering.

**Implications:**

- The `agent_providers/` system (Gemini, Claude) continues unchanged.
- The `GeminiDispatchClient` ACP client logic is preserved and wrapped by the MCP server.
- Future ACP proxy chain support could be added at Layer 3 without affecting Layers 1 or 2.

### 4. Rejected Alternative: A2A for Transport

**Decision:** A2A is NOT used for sub-agent transport despite its rich task semantics.

**Rationale:**

- A2A requires HTTP transport. The stdio proposal (Issue #1074) is not merged into the spec.
- Running localhost HTTP servers per sub-agent introduces unnecessary infrastructure for local subprocess dispatch.
- A2A's task state semantics are valuable and are adopted in the internal task engine (Layer 2), but its transport requirements are not.

### 4a. A2A Convergence Monitoring

**Context:** Google created both A2A and Gemini CLI. Evidence shows active convergence between the two projects:

- A2A client code exists in the Gemini CLI codebase (PR #3079, closed as "not prioritized" but code present in `packages/core/src/a2a/`)
- v0.28-preview adds pluggable A2A auth infrastructure and admin configuration UI
- RFC #7822 proposes standardizing on A2A for all Gemini CLI integrations
- Issue #10482 proposed direct A2A server integration into Gemini CLI (closed as stale, but demonstrates community demand)
- Google donated A2A to the Linux Foundation (June 2025) with 100+ supporting organizations; governance now includes a Technical Steering Committee
- IBM's "ACP" (Agent Communication Protocol) merged into A2A under Linux Foundation governance (September 2025), consolidating two competing agent protocols
- A2A v0.2 added gRPC support and stateless interactions; v0.3 roadmap includes signed Agent Cards and registry patterns
- Stdio transport proposed (Issue #1074, label: TSC Review) but not on the official v0.3 roadmap

Decision 4 rejected A2A transport because it requires HTTP. That rejection remains valid today. However, Decision 4 lacks a contingency for the scenario where Gemini CLI natively bridges A2A over local transport, or where A2A adds stdio support.

**Decision:** Monitor Gemini CLI releases for A2A capability changes. Reassess this decision if any of the following triggers occur:

1. Gemini CLI adds `--a2a` or `--experimental-a2a` flag for local agent communication
2. A2A spec adds stdio transport (Issue #1074 or equivalent is merged and released)
3. A2A spec reaches 1.0 under Linux Foundation governance
4. Gemini CLI's sub-agent registry (v0.27+) adopts A2A task semantics natively

**Contingency:** The `AgentProvider` abstraction at Layer 3 supports adding an `A2AProvider` without modifying the MCP server (Layer 1) or task engine (Layer 2). The provider would implement the same `prepare_process()` interface, though A2A's HTTP requirement may necessitate a different connection model (HTTP client rather than subprocess stdio). See [[2026-02-07-dispatch-a2a-convergence]] for the full analysis.

**Review cadence:** Quarterly, or triggered by any Gemini CLI major/minor release.

## Status

Accepted

## Consequences

**Benefits:**

- Each protocol operates at its designed boundary, eliminating the current misalignment where ACP (Human-to-Agent) is used for Agent-to-Agent.
- MCP at Layer 1 enables tool-agnostic dispatch from any MCP-compatible client.
- ACP at Layer 3 preserves the working subprocess management system.
- The three-layer separation allows independent evolution of each layer.

**Drawbacks:**

- Three protocols increase the conceptual surface area compared to a single-protocol approach.
- MCP Tasks is experimental (2025-11-25 spec) and may evolve.
- The internal task engine is a custom component that must be maintained alongside the protocol layers.

---
feature: dispatch
date: 2026-02-07
related:
  - [[2026-02-07-dispatch-protocol-selection.md]]
  - [[2026-02-07-dispatch-architecture.md]]
  - [[2026-02-07-dispatch-task-contract.md]]
  - [[2026-02-07-dispatch-workspace-safety.md]]
---

# Dispatch Framework: Project Scope and Goals

## Context

The `.rules/scripts/` system currently provides three components:

1. **`cli.py`** -- A resource manager that syncs rules, agents, skills, and configs across three AI tool destinations (`.claude/`, `.gemini/`, `.agent/`).
2. **`acp_dispatch.py`** -- A headless ACP client that spawns sub-agents as subprocesses via the Agent Client Protocol.
3. **`agent_providers/`** -- A pluggable provider abstraction (Gemini, Claude) with capability-tiered model selection (LOW/MEDIUM/HIGH).

An architectural review identified five tensions in the current system:

- ACP (a Human-to-Agent protocol) is being used for Agent-to-Agent delegation.
- The permission model auto-approves everything with no granularity.
- Multiple sub-agents share a mutable workspace with no coordination.
- Task results are unstructured (files written by convention, stdout captured as text).
- Agent discovery is hard-coded (no Agent Cards, no capability negotiation).

This ADR establishes the project's scope and goals to guide all subsequent architectural decisions.

## Decisions

### 1. The Framework is a Full Agent Development Platform

**Decision:** The `.rules/scripts/` system is a comprehensive multi-AI agent orchestration framework, not a simple CLI wrapper.

**Rationale:**

- The existing system already manages agent definitions, provider abstraction, rule sync, and subprocess lifecycle -- this is platform-level infrastructure.
- The project requires sub-agent driven development workflows: research, ADR creation, plan writing, task execution, code review, and documentation curation.
- A full platform enables systematic agent composition (team leads dispatching specialists) rather than ad-hoc script invocations.

**Implications:**

- The dispatcher must support structured task lifecycles, not just fire-and-forget subprocess calls.
- Agent definitions must be machine-readable for dynamic discovery and capability matching.
- The system must be extensible to new providers and protocols without architectural changes.

### 2. The API Must Be Tool-Agnostic

**Decision:** The dispatch interface must be callable from both Gemini CLI and Claude Code (and any future MCP-compatible client) without modification.

**Rationale:**

- The current system supports two providers (Gemini, Claude) but the dispatch entry point (`python acp_dispatch.py`) requires shell access and string escaping, which is fragile across different AI tool contexts.
- Gemini CLI agents and Claude Code agents both need to act as team leads that dispatch sub-agents. Neither should require tool-specific dispatch code.
- Research confirmed that MCP (Model Context Protocol) is the established standard for tool/service interfaces, supported by Claude Code, Gemini, Cursor, VS Code, and others.

**Implications:**

- The dispatch interface must be a typed JSON protocol, not a CLI with string arguments.
- Both Gemini CLI and Claude Code must be able to invoke dispatch without knowing the implementation details.
- The `.mcp.json` configuration file provides git-committable, auto-discovered server registration.

### 3. Python is the Implementation Language

**Decision:** The dispatch framework is implemented in Python, not Rust.

**Rationale:**

- No protocol (ACP, MCP, A2A) mandates a specific implementation language.
- Every production dispatch/orchestration implementation found during research is Python or TypeScript (mcp-agent by LastMile AI, Agent-MCP by rinadelph, claude-code-acp by Zed Industries).
- The existing codebase is 2,200+ lines of tested Python (acp_dispatch.py, cli.py, agent_providers/, 65 tests).
- All three protocol SDKs have official Python support; A2A has no Rust SDK at all.
- The dispatch server is I/O-bound orchestration glue (accept JSON, read files, spawn processes, track state). Python's strengths align; Rust's strengths (memory safety, performance, zero-cost abstractions) do not apply.
- The Rust project is the editor application; the dispatch tooling is infrastructure supporting it.

**Implications:**

- The existing `acp_dispatch.py` and `agent_providers/` code carries forward with refactoring, not rewriting.
- Python MCP SDK (`mcp`) is the server framework.
- Python ACP SDK (`agent-client-protocol`) continues as the sub-agent transport.

## Status

Accepted

## Consequences

**Benefits:**

- Clear scope prevents under-engineering (treating dispatch as a throwaway script) and over-engineering (building a generic agent framework).
- Tool-agnostic API enables both Gemini and Claude team leads to orchestrate sub-agents natively.
- Python implementation preserves 2,200+ lines of existing, tested code and enables rapid iteration during architectural evolution.

**Drawbacks:**

- Full platform scope increases the surface area of the dispatch system beyond simple subprocess management.
- Tool-agnostic API requires protocol compliance (MCP) rather than ad-hoc CLI integration.
- Python as a separate language from the Rust editor requires maintaining two development environments.

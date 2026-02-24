---
tags:
  - "#research"
  - "#protocol"
date: "2026-02-07"
---
# Protocol Review: ACP vs A2A

**Date:** 2026-02-07
**Status:** Research / Ideation
**Scope:** Evaluate whether the current `acp_dispatch.py` architecture correctly uses ACP, and how A2A contrasts.

---

## Protocol Summaries

### ACP (Agent Client Protocol)

- **Relationship:** Human ↔ Agent
- **Analogy:** Language Server Protocol (LSP) for AI agents
- **Transport:** JSON-RPC 2.0 over stdio (local subprocess); HTTP/WS planned for remote
- **Trust model:** Implicit — same machine, same user, editor-supervised
- **Deployment:** Agent is spawned as a child process of the editor
- **Discovery:** None — editor knows which agent to launch

**Core primitives:**

- `initialize` → `session/new` → `session/prompt` → `session/update` (streaming) → response
- Client callbacks: `request_permission`, `fs/read_text_file`, `fs/write_text_file`, `terminal/*`
- The client (editor) provides the environment: filesystem, terminals, permissions
- The agent requests resources through the client

**Design intent:** Decouple code editors from AI agents. Any editor can drive any agent through a standard interface, the same way LSP decoupled editors from language compilers.

### A2A (Agent-to-Agent Protocol)

- **Relationship:** Agent ↔ Agent
- **Analogy:** HTTP/REST for autonomous agent microservices
- **Transport:** JSON-RPC 2.0 over HTTPS; SSE for streaming; gRPC binding available
- **Trust model:** Untrusted/semi-trusted, inter-organizational (OAuth 2.0, API keys, mTLS, OpenID Connect)
- **Deployment:** Agents are independent services on separate servers
- **Discovery:** Agent Cards — self-describing manifests with capabilities, skills, security schemes

**Core primitives:**

- `SendMessage` → `Task` (states: SUBMITTED → WORKING → COMPLETED/FAILED/CANCELED)
- `Artifact` — typed outputs produced by a task (text, binary, URLs, structured JSON)
- `SubscribeToTask` — real-time streaming of status/artifact updates
- Push notifications for async long-running work
- No filesystem or terminal primitives — agents are self-contained

**Design intent:** Enable autonomous agents built on different frameworks by different organizations to discover, negotiate, and collaborate — without exposing internal state or tool implementations.

---

## Relationship Between Protocols

They are **complementary, not competing**.

```
ACP:  Human → Editor/Client → [stdio] → Agent subprocess
      (vertical: human controls agent through an intermediary)

A2A:  Agent A → [HTTPS] → Agent B → [HTTPS] → Agent C
      (horizontal: peers collaborating, no human in the wire)
```

A full-stack architecture might use ACP at the edges (human ↔ primary agent) and A2A in the middle (primary agent ↔ specialist agents on remote servers).

---

## Current Architecture Assessment

### What the codebase does

```
Human → Claude Code (team lead) → acp_dispatch.py (headless ACP client) → Sub-agent (Gemini/Claude)
                                   ↑
                           Simulates an editor environment
                           but is actually another agent
```

The dispatcher (`GeminiDispatchClient`) acts as an ACP client, implementing:

- Permission handling (auto-approves all tool calls — YOLO mode)
- File I/O (workspace-scoped read/write pass-through)
- Terminal management (spawns and tracks subprocesses)
- Session lifecycle (initialize → new_session → prompt loop)

### Architectural misalignment

The dispatcher is using ACP — a Human↔Agent protocol — to implement Agent↔Agent delegation. This works mechanically but introduces five specific tensions:

#### - Permission model is vestigial

ACP's `request_permission` exists for human approval of dangerous operations. The dispatcher rubber-stamps everything. The safety guarantee ACP provides doesn't exist at this layer — it has been pushed up to wherever Claude Code's own permission model lives.

#### - Shared mutable workspace with no coordination

The team lead agent and the sub-agent both have write access to the same filesystem, through different channels, with no locking or conflict resolution. ACP assumes a single agent operates on the workspace at a time, supervised by a human. The current architecture has two agents operating concurrently on the same files.

#### - One-shot delegation, not conversation

ACP's session model supports multi-turn human conversation. The dispatcher sends a task and waits for completion — a task delegation pattern, not a conversation. The interactive mode exists but isn't used by the skill/workflow system.

#### - No task semantics

When the sub-agent finishes, the dispatcher captures stdout text. There is no structured handoff — no artifacts, no status states, no typed outputs. The "result" is that the sub-agent wrote files to `.vault/` by convention, and the team lead reads them afterward. That convention lives entirely outside the protocol.

#### - Discovery and capability negotiation don't exist

The dispatcher hard-codes which agent to load, which model to use, and what provider to spawn. ACP doesn't define discovery because the human already chose their agent. A2A defines Agent Cards for exactly this purpose.

---

## Capability Gap Analysis

| Need | ACP provides | A2A provides |
|---|---|---|
| Spawn local subprocess | Yes | No (assumes independent services) |
| Filesystem pass-through | Yes | No (agents are self-contained) |
| Terminal execution | Yes | No |
| Task lifecycle states | No | Yes (SUBMITTED → WORKING → COMPLETED) |
| Structured artifacts | No (text stream only) | Yes (typed Parts, Artifacts) |
| Agent discovery | No | Yes (Agent Cards) |
| Auth between agents | No (implicit trust) | Yes (OAuth, mTLS) |
| Human approval | Yes | No (no human in wire) |

The dispatcher needs the **process control** of ACP (spawn, stdio, filesystem, terminals) but the **interaction semantics** of A2A (task delegation, structured results, status tracking).

---

## Boundary Confusion

The architecture conflates two distinct communication boundaries:

- **Human ↔ Agent** (ACP's domain) — Claude Code talking to the user
- **Agent ↔ Agent** (A2A's domain) — the team lead delegating to sub-agents

Boundary 2 is currently implemented by faking Boundary 1. The cost:

- No real permissions at the sub-agent layer
- No structured task handoff
- No coordination on shared mutable state
- A dispatcher that simulates an entire editor environment just to send a task to a subprocess

---

## Open Questions for Further Work

- Could a thin A2A-like task layer be built on top of ACP's process control?
- Should the dispatcher introduce its own task state machine (independent of protocol)?
- How should filesystem conflict resolution work when multiple agents share a workspace?
- Is the auto-approve permission model an acceptable risk, or should the team lead agent proxy permission requests upward?
- Would Agent Cards (or a lightweight equivalent) improve the agent selection and fallback logic currently hard-coded in the dispatcher?

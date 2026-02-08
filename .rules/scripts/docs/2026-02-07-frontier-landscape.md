# Frontier Landscape: Agent Protocols and Interoperability

**Date:** 2026-02-07
**Source:** Research agent -- frontier discussions, RFDs, emerging standards
**Scope:** Latest thinking from protocol authors, community discussions, gaps

---

## 1. Critical Disambiguation: Three Different "ACPs"

| Protocol | Full Name | Origin | Focus |
|---|---|---|---|
| ACP (Zed) | Agent Client Protocol | Zed Industries, Aug 2025 | Editor-to-agent (stdin/stdout, JSON-RPC 2.0) |
| ACP (IBM) | Agent Communication Protocol | IBM BeeAI, Mar 2025 | Agent-to-agent (REST/HTTP) |
| ACP (Cisco) | Agent Connect Protocol | Cisco/agntcy | Agent connectivity |

**IBM's ACP merged into A2A** under the Linux Foundation (September 2025).
**Zed's ACP** remains active and independent. v0.10.8 (2026-02-04), 2,000+ stars, 61 contributors, 30 releases.

---

## 2. ACP (Zed) Ecosystem Status

### Adoption
- **25 agents**: Claude Code, Gemini CLI, GitHub Copilot, Goose, Codex CLI, Mistral Vibe, Qwen Code, Kiro CLI, OpenHands, JetBrains Junie (coming)
- **16 clients**: Zed, JetBrains, Neovim (3 plugins), Emacs, Obsidian, marimo, DuckDB, DeepChat

### Agent Registry
Launched January 2026. Live in JetBrains IDE 2025.3+. Four discovery methods: Basic, Open, Registry-Based, Embedded.

### RFD Process
19 RFD documents as of February 2026. Key ones:

| RFD | Significance |
|---|---|
| **proxy-chains** | Most important for agent-to-agent |
| **mcp-over-acp** | Bridges MCP tools into ACP |
| **agent-telemetry-export** | OpenTelemetry monitoring |
| **meta-propagation** | W3C trace context |
| **auth-methods** | OAuth flows |
| **acp-agent-registry** | Discovery |

---

## 3. Proxy Chains RFD -- Key Agent-to-Agent Primitive

Authored by **Niko Matsakis** (nikomatsakis).

### Problem
MCP servers operate "behind" agents and cannot: modify prompts, inject context, transform responses, or coordinate across agents.

### Architecture
```
Client -> Conductor -> Proxy1 -> Proxy2 -> Agent
```

Central **conductor** orchestrates all routing. Single new method: **`proxy/successor`**.

### What Proxies Subsume
AGENTS.md, MCP servers, hooks/steering, subagents, plugins -- all unified into composable proxy components.

### Implementation Status
Working Rust prototype: `sacp`, `sacp-proxy`, `sacp-conductor` in the `symposium-acp` repository.

### Multi-Agent Future
Extending `proxy/successor` with optional `peer` field enables M:N topologies.

---

## 4. SymmACP Vision

Niko Matsakis proposed **SymmACP** (October 2025) -- symmetric ACP capabilities:
- Either side can provide initial conversation state
- An "editor" can provide MCP tools to the "agent"
- Conversations can be serialized with extra state

Vision: **Build AI tools like Unix pipes or browser extensions.**

---

## 5. Claude Code ACP Adapter

**Package**: `@zed-industries/claude-code-acp` v0.15.0 (2026-02-06)

Bridges Claude Code to ACP by translating between ACP, Claude Agent SDK, and Claude's internal protocol. Features: context mentions, images, tool calls, edit review, TODO lists, terminals, slash commands.

---

## 6. Anthropic Agent Teams -- Proprietary Protocol

Released with Opus 4.6 (2026-02-05). **Not ACP-based** -- uses filesystem-based coordination.

| Component | Mechanism |
|---|---|
| Team config | `~/.claude/teams/{team-name}/config.json` |
| Task list | `~/.claude/tasks/{team-name}/` |
| Communication | `SendMessage` tool calls |
| Task states | pending -> in_progress -> completed |

### Differences from ACP Sub-agents

| | Subagents | Agent Teams |
|---|---|---|
| Context | Own window; results return | Own window; independent |
| Communication | Report back only | Direct peer DMs |
| Coordination | Main agent manages | Shared task list |

### Limitations
- No nested teams
- One team per session
- Lead is fixed for lifetime
- Experimental

---

## 7. Emerging IETF Work

| Draft | Topic |
|---|---|
| `draft-narvaneni-agent-uri-02` | `agent://` URI scheme |
| `draft-zyyhl-agent-networks-framework` | AI Agent Networks framework |
| `draft-cui-ai-agent-discovery-invocation` | HTTP-based discovery |
| `draft-liu-agent-context-protocol` | Agent Context Protocol |
| `draft-yl-agent-id-requirements` | Digital Identity for agents |

The `agent://` protocol proposes layered architecture: addressing + transport + capability discovery + orchestration.

---

## 8. Gaps and Open Problems

### 8.1 No Standard Agent-to-Agent Layer in ACP
Proxy chains are orchestration patterns (conductor-mediated), not true peer-to-peer. Community converging on A2A for genuine agent-to-agent.

### 8.2 Protocol Fragmentation
Three "ACP"s + MCP + A2A + ANP + IETF drafts. No unified ontology.

### 8.3 No Cross-Protocol Bridge
No standard bridge between ACP (client) and A2A (agent). Agent spawned via ACP cannot natively discover/delegate to an A2A peer.

### 8.4 Anthropic Agent Teams Are Proprietary
Filesystem-based coordination not exposed via ACP. Non-Claude agents cannot participate.

### 8.5 No Shared Memory Protocol
ACP and A2A both lack robust shared memory. Each teammate has isolated context. No protocol for semantic state transfer.

### 8.6 Security Model Immaturity
Credential delegation, permission scoping across proxy chains, sandboxing -- unsolved.

### 8.7 No Nested Orchestration Standard
Claude Teams prohibit nested teams. ACP proxy chains allow nesting in theory but no implementations demonstrate deep nesting.

---

## 9. Three-Layer Stack Crystallizing

| Layer | Protocol | Status |
|---|---|---|
| Client-to-Agent | ACP (Zed) | Production. 25 agents, 16 clients |
| Agent-to-Tool | MCP (Anthropic) | Production. De facto standard |
| Agent-to-Agent | A2A (Google/LF) | Growing adoption |

### Central Tension

**Anthropic builds vertically-integrated agent teams** while the **open-source community builds horizontally-composable protocol layers**. These must converge for multi-vendor agent interoperability.

---

## Sources

- https://github.com/agentclientprotocol/agent-client-protocol
- https://lfaidata.foundation/communityblog/2025/08/29/acp-joins-forces-with-a2a/
- https://agentclientprotocol.com/rfds/proxy-chains
- https://agentclientprotocol.com/rfds/mcp-over-acp
- https://agentclientprotocol.com/rfds/agent-telemetry-export
- https://agentclientprotocol.com/get-started/agents
- https://agentclientprotocol.com/get-started/clients
- https://smallcultfollowing.com/babysteps/blog/2025/10/08/symmacp/
- https://www.npmjs.com/package/@zed-industries/claude-code-acp
- https://code.claude.com/docs/en/agent-teams
- https://datatracker.ietf.org/doc/draft-narvaneni-agent-uri/02/
- https://blog.jetbrains.com/ai/2026/01/acp-agent-registry/

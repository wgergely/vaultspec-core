---
tags: ["#adr", "#protocol"]
date: 2026-02-15
related:
  - "[[2026-02-15-subagent-adr]]"
  - "[[2026-02-07-a2a-research]]"
  - "[[2026-02-07-protocol-architecture-research]]"
---

## ADR: Cross-Agent Bidirectional Communication — Gemini and Claude via A2A

## Status

**Research Complete** — Feasibility confirmed (8/10). Implementation decision pending.

## Question

How likely is it that Gemini and Claude agents can talk to each other via
bidirectional channels using A2A, ACP, or Claude SDK-like wrappers?

## Answer

**HIGH LIKELIHOOD (8/10).** The protocols, governance, and SDKs all exist or are
converging. No turnkey reference implementation of a Claude agent and a Gemini
agent having a live A2A conversation has been published, but every structural
prerequisite is in place.

---

## Context

### Protocol Landscape (Feb 2026)

Three protocols are relevant — and the naming is a source of real confusion:

| Name | Full Name | Maintainer | Scope | Python Package | Status |
|------|-----------|------------|-------|----------------|--------|
| **ACP** (Zed) | Agent Client Protocol | Zed Industries / agentclientprotocol | Editor-to-agent (vertical) | `agent-client-protocol` v0.8.0 | Active, v0.10.8 |
| **ACP** (IBM) | Agent Communication Protocol | IBM / i-am-bee | Agent-to-agent | (archived) | **Merged into A2A** (Aug 2025) |
| **A2A** | Agent2Agent Protocol | Google → Linux Foundation | Agent-to-agent (horizontal) | `a2a-sdk` v0.3.22 | Active, v0.3.0 spec |

**Critical clarification**: Vaultspec uses **Zed's ACP** (`agent-client-protocol`
package, `import acp`). This is the editor-to-agent protocol over JSON-RPC/stdio.
It is **not** the IBM ACP that merged into A2A. The Zed ACP remains active and
relevant for its purpose (editor↔agent), but it **cannot** do agent-to-agent
communication by design.

### Governance Convergence

In December 2025, the **Agentic AI Foundation (AAIF)** was formed under the Linux
Foundation with platinum members including **Anthropic, Google, Microsoft, OpenAI,
AWS, Block, Bloomberg, Cloudflare**. The anchor projects:

- **MCP** (Anthropic) — agent-to-tool protocol (vertical)
- **A2A** (Google) — agent-to-agent protocol (horizontal)
- **goose** (Block) — open-source AI agent
- **AGENTS.md** (OpenAI) — agent capability descriptions

MCP and A2A are explicitly complementary under shared governance. Both Anthropic
and Google co-founded the same body.

### Native Capabilities

| Capability | Claude | Gemini |
|---|---|---|
| Speaks A2A natively | No | Yes (via Google ADK) |
| Speaks Zed ACP natively | No (bridged via `ClaudeACPBridge`) | Yes (`--experimental-acp`) |
| Speaks MCP (as client) | Yes | Yes |
| Can be wrapped in A2A server | Yes (via `a2a-sdk` `AgentExecutor`) | N/A — native |
| Intra-vendor multi-agent | Yes (Agent Teams, subagents) | Yes (ADK multi-agent) |
| Cross-vendor multi-agent | Not native — bridge required | Not native — bridge required |

---

## Research Findings

### 1. Zed ACP Cannot Do Agent-to-Agent

The Agent Client Protocol (Zed) is explicitly scoped to editor↔agent:

- **Fixed asymmetric roles**: `ClientSideConnection` vs `AgentSideConnection` — an
  agent cannot simultaneously be a client to another agent
- **Stdio-only transport**: requires subprocess parent-child; no network peers
- **No discovery**: no mechanism for agents to find each other
- **No delegation**: no primitive for agent-to-agent coordination

The `extMethod()`/`extNotification()` extension points could theoretically carry
custom inter-agent messages, but this would be non-standard and unsupported.

**Conclusion**: Zed ACP is the right protocol for our orchestrator↔agent
communication (and should be kept for that purpose), but it is the **wrong
protocol** for agent-to-agent bidirectional messaging.

### 2. A2A Is Purpose-Built for This

A2A v0.3.0 provides everything needed:

- **Agent Cards**: JSON capability manifests for agent discovery (identity, skills,
  auth schemes, supported bindings)
- **11 RPC operations**: `SendMessage`, `SendStreamingMessage`, `GetTask`,
  `ListTasks`, `CancelTask`, `SubscribeToTask`, push notification CRUD,
  `GetExtendedAgentCard`
- **Task lifecycle**: submitted → working → input-required → completed | failed |
  canceled | rejected
- **Three transports**: HTTP+JSON/REST, gRPC, JSON-RPC 2.0 over HTTP (with SSE)
- **Enterprise auth**: API keys, OAuth 2.0, OpenID Connect, Mutual TLS
- **Opaque execution**: agents collaborate without exposing internals
- **21.9k GitHub stars**, 5 language SDKs, Linux Foundation governance

### 3. Claude's Cross-Agent Position

- **Claude Agent SDK**: Native subagent support (hierarchical parent→child only).
  No peer-to-peer. No A2A.
- **Claude Code Agent Teams**: Peer-to-peer via `SendMessage` tool, but proprietary
  file-based protocol. Experimental. Intra-Claude only.
- **MCP Connector**: Claude API has built-in MCP client — can consume tools from any
  MCP server. But Claude does NOT expose an MCP server interface for others.
- **Agent Skills**: Open standard at agentskills.io. Capability description format,
  not a communication protocol. Adopted by AAIF.
- **Bridge pattern**: Claude agents can be wrapped in A2A-compatible service layers.
  Anthropic published a webinar: "Deploying multi-agent systems using MCP and A2A
  with Claude on Vertex AI."

### 4. Gemini's Cross-Agent Position

- **Google ADK**: Native A2A support. Also supports Claude models via `Claude`
  wrapper class.
- **Native ACP**: `gemini --experimental-acp` for editor integration.
- **Agent Engine**: Supports deploying agents regardless of framework or model.
- **A2A Agent Cards**: First-class concept in ADK.

### 5. How Bidirectional Communication Would Work

```
┌──────────────────────┐       A2A (HTTP/JSON-RPC)       ┌──────────────────────┐
│    Claude Agent       │◄──────────────────────────────►│    Gemini Agent       │
│                       │                                 │                       │
│  Claude Agent SDK     │   Agent Cards for discovery     │  Google ADK           │
│  wrapped in a2a-sdk   │   SendMessage bidirectional     │  (native A2A)         │
│  AgentExecutor        │   Task lifecycle states         │                       │
│                       │   SSE for streaming             │                       │
│  MCP for tools ───────┤                                 ├─── MCP for tools      │
└──────────────────────┘                                 └──────────────────────┘
```

Each agent exposes an A2A Agent Card at a well-known URL. Discovery via Agent Card
fetch. Communication via `SendMessage` over HTTP with task lifecycle management.
Streaming via SSE.

---

## Vaultspec Architecture Readiness

### What's Already In Place

| Asset | Location | Readiness |
|-------|----------|-----------|
| `a2a-sdk` v0.3.22 installed | pyproject.toml, .venv | Ready |
| `TaskEngine.input_required` state | `orchestration/task_engine.py` | Maps to A2A `input-required` |
| `ext_method`/`ext_notification` stubs | `acp/client.py`, `acp/claude_bridge.py` | Extension hooks present |
| `ProcessSpec.mcp_servers` | `providers/base.py` | Agents can receive tool configs |
| MCP dispatch pattern | `vs-subagent-mcp` | One-way agent→agent works today |
| A2A research docs | `.vault/research/2026-02-07-a2a-*` | Prior research available |
| `A2AStarletteApplication` | `a2a.server.apps` | Ready for HTTP server |
| `AgentCard`, `AgentSkill` types | `a2a.types` | Ready for agent discovery |

### What Needs to Be Built

1. **A2A `AgentExecutor` wrapper** for Claude agents (wraps `ClaudeACPBridge` or
   direct Agent SDK in an A2A server)
2. **A2A Agent Card generation** for each vaultspec agent definition
3. **Agent discovery/registry** — Agent Card hosting and lookup
4. **A2A ↔ ACP bridge** in the orchestrator (orchestrator speaks ACP to agents
   internally, A2A externally for peer communication)
5. **Task state mapping**: A2A task states ↔ `TaskEngine` states

---

## Feasibility Scorecard

| Dimension | Score | Evidence |
|---|---|---|
| Protocol maturity | 7/10 | A2A v0.3.0 comprehensive but pre-1.0 |
| SDK availability | 8/10 | `a2a-sdk` v0.3.22, ADK native, Claude Agent SDK |
| Governance alignment | 10/10 | Anthropic + Google co-founded AAIF |
| Cross-vendor design | 9/10 | A2A is explicitly vendor-neutral and opaque |
| Public examples | 3/10 | No published Claude↔Gemini A2A reference |
| Production maturity | 5/10 | Pre-1.0, ADK A2A is "experimental" |
| Vaultspec readiness | 6/10 | Good hooks, `a2a-sdk` installed, migration needed |
| **Overall** | **8/10** | **Engineering task, not research question** |

---

## Installed Packages Audit

### Current State (Feb 2026)

```
agent-client-protocol  0.8.0   # Zed ACP — editor↔agent stdio protocol
a2a-sdk                0.3.22  # Google A2A — agent↔agent HTTP protocol
mcp                    1.26.0  # Anthropic MCP — agent↔tool protocol
claude-agent-sdk       0.1.30+ # Claude Agent SDK — wraps Claude CLI
```

### Clarification of "ACP"

The codebase has **zero naming confusion** at the code level — every `import acp`
and `from acp.schema import ...` refers to Zed's `agent-client-protocol` package.
The IBM ACP (which merged into A2A) was never used in this codebase. The `a2a-sdk`
is installed but has zero import references in production code.

### Migration Implications

- **`agent-client-protocol` is NOT deprecated**. It is Zed's editor↔agent protocol
  (v0.10.8, active development). It serves a different purpose than A2A.
- **IBM's ACP IS deprecated** (merged into A2A). But we never used it.
- **No migration from ACP→A2A is needed for current functionality**. The Zed ACP
  orchestrator↔agent communication pattern is correct and should be preserved.
- **A2A is ADDITIVE** — it adds agent-to-agent on top of existing ACP
  orchestrator↔agent.

### Recommended Protocol Stack

```
MCP  (agent-to-tool)      — keep, expand (vault RAG MCP server)
ACP  (orchestrator-to-agent) — keep as-is (Zed protocol, stdio)
A2A  (agent-to-agent)     — add new layer (HTTP, agent cards)
```

---

## Decision

### Short-term (Current)

Keep existing architecture unchanged. Zed ACP for orchestrator↔agent communication
is correct. No migration needed.

### Medium-term (Next Phase)

Add A2A as a new layer for agent-to-agent communication:

1. Implement `AgentExecutor` wrapper around vaultspec agents
2. Generate Agent Cards from agent definition files
3. Expose agents as A2A HTTP servers via `A2AStarletteApplication`
4. Map `TaskEngine` states to A2A task lifecycle

### Long-term

Full MCP + ACP + A2A stack:

- MCP for tool access (vault search, vault get, etc.)
- ACP for editor/orchestrator↔agent communication (stdio)
- A2A for peer agent↔agent collaboration (HTTP)

---

## Risks

1. **A2A pre-1.0 instability**: v0.3.x may break before 1.0. Mitigated by thin
   wrapper layer isolating A2A from core logic.
2. **No reference implementation**: First-mover risk building Claude↔Gemini A2A.
   Mitigated by strong SDK availability on both sides.
3. **Naming confusion**: "ACP" means two different things in the AI agent ecosystem.
   Mitigated by this ADR documenting the distinction.
4. **Latency overhead**: A2A HTTP transport adds network latency vs stdio ACP.
   Acceptable for agent collaboration tasks.

## Sources

- [A2A Protocol Spec v0.3.0](https://a2a-protocol.org/latest/) (21.9k GitHub stars)
- [A2A Python SDK](https://github.com/a2aproject/a2a-python) (v0.3.22)
- [ACP (Zed) Protocol](https://github.com/agentclientprotocol/agent-client-protocol) (v0.10.8)
- [ACP merges into A2A](https://lfaidata.foundation/communityblog/2025/08/29/acp-joins-forces-with-a2a-under-the-linux-foundations-lf-ai-data/) (Aug 2025)
- [AAIF Formation](https://www.linuxfoundation.org/press/linux-foundation-announces-the-formation-of-the-agentic-ai-foundation) (Dec 2025)
- [Anthropic: MCP + A2A Webinar](https://www.anthropic.com/webinars/deploying-multi-agent-systems-using-mcp-and-a2a-with-claude-on-vertex-ai)
- [Google ADK A2A Integration](https://google.github.io/adk-docs/a2a/)
- [Google ADK Claude Support](https://google.github.io/adk-docs/agents/models/anthropic/)
- [Claude Agent SDK](https://platform.claude.com/docs/en/agent-sdk/overview)
- [Claude Code Agent Teams](https://code.claude.com/docs/en/agent-teams)

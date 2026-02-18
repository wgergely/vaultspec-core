---
tags: ["#research", "#protocol"]
date: 2026-02-07
related:
  - "[[2026-02-07-acp-research]]"
  - "[[2026-02-07-a2a-research]]"
  - "[[2026-02-07-multi-agent-orchestration-research]]"
  - "[[2026-02-07-frontier-landscape-research]]"
  - "[[2026-02-07-protocol-review-research]]"
---

# Protocol Architecture for Sub-Agent Driven Development

**Date:** 2026-02-07
**Status:** Research / Architecture
**Scope:** How to correctly implement agent dispatch, delegation, and bidirectional communication using the right protocols for each boundary.

---

## The Three-Layer Protocol Stack

The AI agent ecosystem is crystallizing around three complementary protocol layers. Each serves a distinct communication boundary.

| Layer | Protocol | Boundary | Transport | Status |
|---|---|---|---|---|
| **Client-to-Agent** | ACP (Zed) | Human ↔ Agent | JSON-RPC 2.0 / stdio | Production. 25 agents, 16 clients |
| **Agent-to-Tool** | MCP (Anthropic) | Agent ↔ Tool/Resource | JSON-RPC 2.0 / stdio/HTTP | De facto standard |
| **Agent-to-Agent** | A2A (Google/LF) | Agent ↔ Agent | JSON-RPC 2.0 / HTTPS/SSE/gRPC | Growing adoption. 150+ orgs |

**Key insight**: These are not competing protocols — they are complementary layers. An agent can simultaneously speak ACP to its editor, MCP to its tools, and A2A to peer agents.

---

## Protocol Deep Dive

### ACP — The Client-Agent Layer

**Purpose**: Decouple code editors from AI agents, the same way LSP decoupled editors from language compilers.

**Architecture**: The editor (client) spawns the agent as a subprocess over stdio. Communication is bidirectional JSON-RPC 2.0. The editor provides the environment (filesystem, terminals, permissions), while the agent requests resources through the editor.

**Lifecycle**:

```
Client                          Agent
  |--- initialize ------------->|     (version + capability negotiation)
  |--- session/new ------------->|     (cwd, MCP servers)
  |--- session/prompt --------->|     (user message + context)
  |<--- session/update (plan) --|     (streaming updates)
  |<--- session/update (tool) --|
  |<--- request_permission -----|     (agent needs approval)
  |--- permission response ---->|
  |<--- session/update (text) --|
  |<--- prompt response --------|     (stopReason: end_turn)
```

**Key capabilities**:

- File I/O: `fs/read_text_file`, `fs/write_text_file`
- Terminal: `terminal/create`, `terminal/output`, `terminal/wait_for_exit`, `terminal/kill`, `terminal/release`
- Permission system: `request_permission` with `allow_once`, `allow_always`, `reject_once`, `reject_always`
- Session modes, plans, tool call tracking
- MCP server provisioning via `session/new`

**Proxy Chains (RFD)**: The most significant upcoming ACP extension. A conductor orchestrates a chain of proxy components between client and agent. Single new method: `proxy/successor`. Proxies can inject prompts, add context, provision MCP servers, filter tools. Working Rust prototype exists (`sacp`, `sacp-proxy`, `sacp-conductor`).

**What ACP is NOT**: A protocol for agent-to-agent communication. It assumes a human operator on the client side, with implicit trust (same machine, same user). No discovery mechanism, no structured task handoff, no cross-network capability.

> Full reference: [2026-02-07-acp-research.md](./2026-02-07-acp-research.md)

### A2A — The Agent-Agent Layer

**Purpose**: Enable autonomous agents built on different frameworks, by different organizations, to discover, negotiate, and collaborate without exposing internal state.

**Architecture**: Agents are independent HTTP services. Discovery happens through Agent Cards served at `/.well-known/agent-card.json`. Communication uses JSON-RPC 2.0 over HTTPS with SSE for streaming and optional push notifications.

**Task state machine** (9 states):

```
submitted --> working --> input_required --> completed
                    \                   /
                     --> failed / canceled / rejected / auth_required
```

**Core data types**:

- **Task**: UUID, context_id, status, artifacts, history, metadata
- **Message**: role (USER/AGENT), parts (text, binary, URL, structured JSON)
- **Artifact**: Named, described output with typed parts
- **AgentSkill**: Describes what an agent can do, with examples and I/O modes

**Service definition** (11 RPCs):

- `SendMessage` / `SendStreamingMessage` — initiate interaction
- `GetTask` / `ListTasks` / `CancelTask` — task lifecycle
- `SubscribeToTask` — real-time streaming
- Push notification CRUD — webhook-based async delivery
- `GetExtendedAgentCard` — authenticated discovery

**Security**: API keys, HTTP auth (Bearer/Basic), OAuth 2.0 (authorization code, client credentials, device code), OpenID Connect, mTLS.

**Python SDK** (`a2a-sdk`):

```python
class AgentExecutor(ABC):
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None: ...
    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None: ...
```

> Full reference: [2026-02-07-a2a-research.md](./2026-02-07-a2a-research.md)

### - MCP — The Agent-Tool Layer

**Purpose**: Connect AI models to external tools and resources. Complementary to both ACP and A2A.

**Bridge potential**: The `mcp-over-acp` RFD enables MCP servers to communicate through ACP channels. Methods: `mcp/connect`, `mcp/message`, `mcp/disconnect`. Agents advertise support via `mcpCapabilities.acp: true`.

---

## Real-World Orchestration Patterns

### - Claude Code Agent Teams (Anthropic)

Released with Opus 4.6 (February 2026). **Proprietary**, filesystem-based coordination.

```
      Team Lead (Coordination)
       /         |         \
  Teammate A  Teammate B  Teammate C
       \         |         /
    Shared Task List + Direct DMs
```

**Coordination primitives**:

- `Teammate(spawnTeam)` / `Teammate(cleanup)` — team lifecycle
- `SendMessage(message/broadcast/shutdown_request)` — communication
- `TaskCreate/TaskUpdate/TaskList` — shared task list
- Task states: `pending` → `in_progress` → `completed`
- Dependencies via `blockedBy`

**Strengths**: Peer DMs, parallel execution, cross-process communication, shared task list.
**Limitations**: No session resumption, concurrent file edits cause conflicts, no nested teams, one team per session, proprietary (non-Claude agents cannot participate).

### - Google ADK + A2A

The only cross-boundary solution. Remote agents appear identical to local sub-agents from the orchestrator's perspective.

```python
remote_agent = RemoteA2aAgent(
    name="approval_service",
    agent_card="https://approvals.example.com/.well-known/agent.json",
)
root_agent = Agent(
    sub_agents=[local_agent, remote_agent],  # Both local and remote
)
a2a_app = to_a2a(root_agent)  # Wrap any agent as A2A server
```

**Key characteristic**: Protocol-mediated federation. Agents can be anywhere on the network. Discovery, negotiation, and collaboration happen through A2A's standard primitives.

### - OpenAI Agents SDK

Function-based handoffs. Linear chain topology — the agent with control owns the conversation. Full history passes with each handoff.

```
Triage Agent -> handoff -> Specialist A
                       \-> Specialist B
```

Stateless, no parallelism, no shared state.

### - LangGraph Supervisor

Graph-based routing with checkpointing and shared memory (`InMemoryStore`). Supervisor re-routes based on worker results.

### - Magentic-One (AutoGen)

Dual-loop planning: outer loop (Task Ledger with facts/plan) and inner loop (Progress Ledger for self-reflection). If progress stalls, re-enters outer loop and replans. Most sophisticated but heaviest overhead.

> Full survey: [2026-02-07-multi-agent-orchestration-research.md](./2026-02-07-multi-agent-orchestration-research.md)

---

## Comparative Matrix

| Dimension | Claude Teams | OpenAI SDK | LangGraph | Magentic-One | CrewAI | ADK+A2A |
|---|:-:|:-:|:-:|:-:|:-:|:-:|
| Topology | Star + P2P | Chain | Star | Star | Star | Tree + Remote |
| Peer DMs | Yes | No | No | No | Yes | No |
| Shared Tasks | Yes | No | Graph state | Ledgers | Task context | A2A tasks |
| Parallel | Yes | No | Via nodes | One-at-a-time | Sequential | Via sub-agents |
| Cross-process | Yes | No | No | No | No | Yes (HTTP) |
| Cross-network | No | No | No | No | No | Yes (A2A) |
| Protocol | Proprietary | Proprietary | Proprietary | Proprietary | Proprietary | A2A (open) |

---

## Our Current Architecture and Its Misalignment

### What We Have

```
Human → Claude Code (team lead) → acp_dispatch.py (headless ACP client) → Sub-agent (Gemini/Claude)
                                   ↑
                           Simulates an editor environment
                           but is actually another agent
```

The dispatcher (`GeminiDispatchClient`) uses ACP — a Human↔Agent protocol — to implement Agent↔Agent delegation. It works mechanically, but creates five specific tensions:

| Tension | Problem |
|---|---|
| **Vestigial permissions** | `request_permission` exists for human approval. Dispatcher rubber-stamps everything. |
| **Shared mutable workspace** | Two agents write to the same filesystem with no locking or conflict resolution. |
| **One-shot delegation** | ACP's multi-turn conversation model is used for task delegation, not conversation. |
| **No task semantics** | No structured handoff — results are files written by convention, not protocol artifacts. |
| **No discovery** | Agent selection and model fallback are hard-coded, not negotiated. |

### What We Need

The dispatcher needs the **process control** of ACP (spawn subprocess, stdio, filesystem, terminals) combined with the **interaction semantics** of A2A (task delegation, structured results, status tracking, discovery).

| Need | ACP Provides | A2A Provides |
|---|---|---|
| Spawn local subprocess | Yes | No |
| Filesystem pass-through | Yes | No |
| Terminal execution | Yes | No |
| Task lifecycle states | No | Yes |
| Structured artifacts | No | Yes |
| Agent discovery | No | Yes |
| Auth between agents | No | Yes |
| Human approval | Yes | No |

---

## Gaps and Open Problems in the Ecosystem

### - No Standard Agent-to-Agent Layer in ACP

Proxy chains are conductor-mediated orchestration patterns, not true peer-to-peer. The community is converging on A2A for genuine agent-to-agent communication.

### - Protocol Fragmentation

Three different "ACPs" (Zed, IBM/now-A2A, Cisco) + MCP + A2A + ANP + IETF drafts. No unified ontology.

### - No Cross-Protocol Bridge

No standard bridge between ACP (client layer) and A2A (agent layer). An agent spawned via ACP cannot natively discover or delegate to an A2A peer.

### - Proprietary Agent Teams

Anthropic's Agent Teams use filesystem-based coordination not exposed via any standard protocol. Non-Claude agents cannot participate.

### - No Shared Memory Protocol

Both ACP and A2A lack robust shared memory. Each teammate has an isolated context window. No protocol exists for semantic state transfer between agents.

### - Security Model Immaturity

Credential delegation, permission scoping across proxy chains, sandboxing — all unsolved at the protocol level.

### - No Nested Orchestration Standard

Claude Teams prohibit nested teams. ACP proxy chains allow nesting in theory but no implementations demonstrate deep nesting. No standard for hierarchical agent orchestration.

---

## Emerging Standards and Future Direction

### IETF Work

| Draft | Topic |
|---|---|
| `draft-narvaneni-agent-uri-02` | `agent://` URI scheme |
| `draft-zyyhl-agent-networks-framework` | AI Agent Networks framework |
| `draft-cui-ai-agent-discovery-invocation` | HTTP-based discovery |
| `draft-liu-agent-context-protocol` | Agent Context Protocol |
| `draft-yl-agent-id-requirements` | Digital Identity for agents |

### ACP Proxy Chains

The closest existing mechanism within ACP for agent-to-agent patterns. Central conductor orchestrates routing through composable proxy components. Future extension: optional `peer` field in `proxy/successor` for M:N topologies.

### SymmACP Vision

Niko Matsakis proposed symmetric ACP capabilities (October 2025): either side can provide initial conversation state, editors can provide MCP tools to agents, conversations can be serialized. Vision: "Build AI tools like Unix pipes or browser extensions."

### ACP Agent Registry

Launched January 2026. Live in JetBrains IDE 2025.3+. Four discovery methods: Basic, Open, Registry-Based, Embedded. 19 RFD documents as of February 2026.

---

## The Central Tension

**Anthropic builds vertically-integrated agent teams** (proprietary, filesystem-based, Claude-only) while the **open-source community builds horizontally-composable protocol layers** (ACP + MCP + A2A).

For our architecture — sub-agent driven development where agents report to a team lead and communicate with peers — we sit at the intersection of both approaches:

- We need ACP's **local process control** (spawn subprocesses, pass filesystem, run terminals)
- We need A2A's **task semantics** (structured delegation, status tracking, artifacts, discovery)
- We want the **multi-vendor flexibility** of open protocols (not locked into Claude-only teams)

### Architectural Options

- **Thin A2A-like task layer on top of ACP process control**: Keep `acp_dispatch.py` for subprocess management but add task state machine, structured artifacts, and status tracking on top. Pragmatic near-term.

- **Full A2A adoption for agent-agent communication**: Stand up sub-agents as A2A services. Clean protocol separation but requires HTTP transport and service infrastructure overhead for what are currently local subprocesses.

- **ACP Proxy Chains**: Use the emerging conductor/proxy architecture. Proxies can inject context, provision tools, transform responses. Most aligned with ACP's direction but still in RFD stage.

- **Hybrid**: ACP for transport (subprocess, stdio, filesystem) + A2A semantics for task lifecycle (states, artifacts, discovery) encoded as conventions on top of ACP messages. A pragmatic bridge until the ecosystem converges.

---

## Recommendations for Our System

### Near-Term (Current Sprint)

- **Acknowledge the boundary confusion**: The dispatcher conflates client-agent and agent-agent communication. Document this explicitly in the codebase.

- **Add task semantics to dispatch results**: Introduce a structured result envelope that wraps sub-agent output with task state, timing, and artifact references — independent of the transport protocol.

- **Formalize the filesystem convention**: The current implicit contract (sub-agent writes to `.vault/`, team lead reads afterward) should become an explicit protocol with defined output paths, artifact manifests, and conflict detection.

### Medium-Term (Next Phase)

- **Implement Agent Cards for sub-agent discovery**: Replace hard-coded agent selection with lightweight discovery manifests that describe capabilities, supported task types, and model tiers.

- **Add a task state machine to the dispatcher**: `submitted → working → input_required → completed/failed`. Enable the team lead to track sub-agent progress and react to failures.

- **Evaluate ACP proxy chains**: As the RFD matures and the Rust prototype stabilizes, assess whether proxy chains can replace the current dispatcher architecture entirely.

### Long-Term (Architecture Evolution)

- **Bridge ACP and A2A**: When a standard bridge emerges, adopt it to enable sub-agents spawned via ACP to discover and delegate to remote A2A peers.

- **Support multi-vendor agent teams**: Move away from Claude-only or Gemini-only delegation toward protocol-mediated federation where any agent speaking the right protocol can participate.

---

## Reference Documents

| Document | Scope |
|---|---|
| [Protocol Review](./2026-02-07-protocol-review-research.md) | Initial ACP vs A2A analysis and architectural diagnosis |
| [ACP Protocol Reference](./2026-02-07-acp-research.md) | Full ACP spec: init, sessions, prompts, tools, permissions, proxy chains, SDKs |
| [A2A Protocol Reference](./2026-02-07-a2a-research.md) | Full A2A spec: RPCs, task states, data types, Agent Cards, SDKs |
| [Multi-Agent Orchestration Survey](./2026-02-07-multi-agent-orchestration-research.md) | Cross-framework comparison: Claude Teams, OpenAI, LangGraph, Magentic-One, CrewAI, ADK |
| [Frontier Landscape](./2026-02-07-frontier-landscape-research.md) | Three ACPs, proxy chains, SymmACP, IETF drafts, gaps, three-layer stack |

---

## Sources

- <https://agentclientprotocol.com/protocol>
- <https://agentclientprotocol.com/rfds/proxy-chains>
- <https://agentclientprotocol.com/rfds/mcp-over-acp>
- <https://a2a-protocol.org/latest/specification/>
- <https://github.com/a2aproject/A2A>
- <https://github.com/agentclientprotocol/agent-client-protocol>
- <https://smallcultfollowing.com/babysteps/blog/2025/10/08/symmacp/>
- <https://code.claude.com/docs/en/agent-teams>
- <https://github.com/openai/openai-agents-python>
- <https://github.com/langchain-ai/langgraph-supervisor-py>
- <https://microsoft.github.io/autogen/stable/>
- <https://docs.crewai.com/en/concepts/collaboration>
- <https://google.github.io/adk-docs/a2a/>
- <https://lfaidata.foundation/communityblog/2025/08/29/acp-joins-forces-with-a2a/>
- <https://www.npmjs.com/package/@zed-industries/claude-code-acp>
- <https://blog.jetbrains.com/ai/2026/01/acp-agent-registry/>
- <https://datatracker.ietf.org/doc/draft-narvaneni-agent-uri/02/>

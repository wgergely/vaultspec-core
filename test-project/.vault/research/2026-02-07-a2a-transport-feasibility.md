---
tags:
  - "#research"
  - "#dispatch"
date: 2026-02-07
related:
  - "[[2026-02-07-dispatch-a2a-convergence]]"
  - "[[2026-02-07-dispatch-protocol-selection]]"
  - "[[2026-02-07-dispatch-task-contract]]"
  - "[[2026-02-07-dispatch-architecture]]"
---

# dispatch research: A2A Transport Feasibility Study

This study evaluates whether A2A (Agent-to-Agent Protocol) can serve as a transport layer for our dispatch framework's sub-agent communication (Layer 3). The assessment is grounded in the current A2A specification (v0.2+), the Gemini CLI codebase, and our existing `AgentProvider` architecture. The conclusion is that A2A is **not feasible today** as a subprocess transport due to its mandatory HTTP requirement, but the architecture is prepared for future adoption.

## Findings

### 1. A2A Transport Requirements

A2A defines three protocol bindings (as of specification v0.2):

| Binding | Transport | Status | Requirement Level |
|---|---|---|---|
| JSON-RPC 2.0 | HTTP/HTTPS with SSE streaming | Mandatory | Required for compliance |
| gRPC | HTTP/2 with protobuf | Optional | Added in v0.2 |
| Custom bindings | Per guidelines | Optional | Must satisfy data mapping, error handling, and streaming requirements |

**Key architectural implications:**

- Every A2A agent MUST expose an HTTP endpoint. The specification defines discovery via Agent Cards served at `/.well-known/agent-card.json`.
- Streaming uses Server-Sent Events (SSE) over HTTP -- the agent pushes task state updates to the client via a persistent HTTP connection.
- Authentication is designed for network boundaries: OAuth 2.0, mTLS, and API keys are the specified mechanisms.
- gRPC support (added in v0.2) still requires HTTP/2 transport -- it does not introduce a non-HTTP option.
- The "Custom Binding Guidelines" section permits extensibility, but custom bindings must satisfy all normative requirements for data type mapping, service parameter transmission, error handling, and streaming support. Stdio is not mentioned as a candidate.

**Sources:** [A2A Protocol Specification](https://a2a-protocol.org/latest/specification/), [A2A Roadmap](https://a2a-protocol.org/latest/roadmap/)

### 2. Stdio Transport Gap

**Issue #1074: "[Feat]: Stdio transport"** (opened September 16, 2025)

This community proposal requests adding stdio transport to the A2A specification, modeled after the Language Server Protocol (LSP) message format:

- **Format:** Header part (Content-Length, Content-Type) followed by a JSON-RPC message body, identical to LSP except message content is A2A instead of LSP.
- **Motivation:** Many agent systems already use stdio for local communication (MCP servers in Cursor/Zed/Gemini CLI, Language Servers). Stdio eliminates port management, simplifies lifecycle (subprocess dies with parent), and is familiar to tool developers.
- **Arguments for:** Eliminates port conflicts, ties agent/client lifecycle naturally, aligns with how MCP servers are already launched.
- **Arguments against:** Hides subprocess execution from host applications, makes configuration cumbersome (command strings vs structured env), removes host flexibility for alternative launch mechanisms (Docker Compose, container orchestration).
- **Current status:** Open, labeled "TSC Review" (requires Technical Steering Committee evaluation).
- **Roadmap inclusion:** NOT listed on the official v0.3 roadmap. The v0.3 roadmap focuses on Agent Card endpoint changes, SDK improvements, signed Agent Cards, and agent registry patterns.

**Assessment:** Stdio transport is under active consideration but has not been prioritized. The TSC label indicates governance-level review is needed, which typically means the proposal has architectural implications that require broader consensus. Given its absence from the v0.3 roadmap, this is unlikely to ship in the near term (3-6 months).

**Source:** [Issue #1074](https://github.com/a2aproject/A2A/issues/1074)

### 3. A2AProvider Architecture Analysis

Our Layer 3 architecture centers on two constructs from `agent_providers/base.py`:

**`ProcessSpec` dataclass:**

```python
@dataclass
class ProcessSpec:
    executable: str        # e.g., "gemini", "npx"
    args: List[str]        # e.g., ["--experimental-acp", "--model", "..."]
    env: Dict[str, str]    # environment variables
    cleanup_paths: List[pathlib.Path]  # temp files to delete
    session_meta: Dict[str, Any]      # ACP session metadata
    initial_prompt_override: Optional[str]
    mcp_servers: List[Dict[str, Any]]  # MCP servers to forward
```

**`AgentProvider` ABC:**

```python
class AgentProvider(abc.ABC):
    def prepare_process(self, agent_name, agent_meta, agent_persona,
                        task_context, root_dir, model_override) -> ProcessSpec
```

**The fundamental mismatch:** `ProcessSpec` assumes the agent is a subprocess launched with an executable + args, communicating over stdio. A2A agents are HTTP servers that receive requests at a URL endpoint. This creates a structural incompatibility:

| Dimension | ProcessSpec (subprocess/stdio) | A2A (HTTP server) |
|---|---|---|
| **Launch** | `executable` + `args` -> subprocess | Agent is a running HTTP server at a URL |
| **Discovery** | Implicit (we know the executable) | Agent Card at `/.well-known/agent-card.json` |
| **Communication** | stdin/stdout JSON-RPC | HTTP POST/GET with SSE |
| **Lifecycle** | Subprocess dies with parent | Independent HTTP server lifecycle |
| **Auth** | Implicit trust (same user, same machine) | OAuth 2.0, mTLS, API keys |
| **Session** | ACP `session/new` -> `session/prompt` | A2A `tasks/send` -> poll/subscribe |

**Key question: Can A2A fit the subprocess model?**

Technically yes, via a wrapper approach: launch an A2A agent as a subprocess (`node a2a-server.js --port 0`), let it pick an ephemeral port, read the port from stdout, then communicate via HTTP to `localhost:{port}`. This is how some development tools handle Language Servers that use HTTP (e.g., OmniSharp). However, this introduces:

- Port management complexity (allocation, conflict detection, cleanup)
- HTTP client dependency in the dispatch loop (currently pure stdio/JSON-RPC)
- Agent Card fetching and capabilities negotiation before task dispatch
- A fundamentally different communication pattern within the same dispatch loop

The dispatch loop in `acp_dispatch.py` (`run_dispatch()`, lines 503-752) is built entirely around ACP's interactive session model: `initialize -> session/new -> session/prompt -> stream response`. An A2A dispatch loop would be: `GET agent-card -> POST tasks/send -> SSE subscribe -> collect artifacts`. These are structurally different patterns that cannot share a single dispatch loop without significant abstraction.

### 4. Task State Mapping

**Our 5-state model** (per ADR [[2026-02-07-dispatch-task-contract]], Decision 1):

```
working -> completed | input_required | failed | cancelled
input_required -> working (resumed) | completed | failed | cancelled
```

**A2A 9-state model:**

```
submitted -> working -> completed | input_required | failed | canceled | rejected
                     -> auth_required -> working (resumed)
input_required -> working (resumed) | completed | failed | canceled
unknown (error/fallback state)
```

**Detailed mapping:**

| A2A State | Our State | Direction | Notes |
|---|---|---|---|
| `submitted` | -- (skip) | A2A -> ours | We create tasks directly in `working`. MCP tool calls are synchronous at invocation, so `submitted` has no equivalent moment. |
| `working` | `working` | Bidirectional | Direct 1:1. |
| `input_required` | `input_required` | Bidirectional | Direct 1:1. Both protocols pause task execution pending client input. |
| `completed` | `completed` | Bidirectional | Direct 1:1. Both are terminal. |
| `failed` | `failed` | Bidirectional | Direct 1:1. Both are terminal. |
| `canceled` | `cancelled` | Bidirectional | Spelling difference only (`canceled` vs `cancelled`). Both are terminal. |
| `rejected` | `failed` | A2A -> ours | No equivalent concept in subprocess dispatch (agents cannot reject tasks). Map to `failed` with `error: "Task rejected by agent"` metadata. |
| `auth_required` | `failed` | A2A -> ours | Not applicable to local subprocess dispatch. Map to `failed` with `error: "Agent requires authentication"` metadata. If A2A remote dispatch is added, this could map to a new `auth_required` state or to `input_required` with auth context. |
| `unknown` | `failed` | A2A -> ours | Error/fallback state. Map to `failed` with `error: "Unknown agent state"` metadata. |

**State extension implications:** If A2A transport is adopted, the task engine (`task_engine.py`) may need to extend from 5 to 7 states (adding `submitted` and `auth_required`) to faithfully represent remote agent interactions. However, for MVP A2A support, the 5-state model suffices with metadata-augmented `failed` states for `rejected`, `auth_required`, and `unknown`.

### 5. Layer Impact Analysis

**Layer 1: MCP Server (`mcp_dispatch.py`) -- No change required.**

The MCP server exposes `dispatch_agent`, `get_task_status`, `list_agents`, and `cancel_task`. These are transport-agnostic: the MCP server calls the task engine and delegates to a provider. Whether the provider uses ACP/stdio or A2A/HTTP is invisible to the MCP interface. The tool schemas do not expose transport details.

**Layer 2: Task Engine (`task_engine.py`) -- Possible state extension.**

The `TaskStatus` enum and `_VALID_TRANSITIONS` map would need extension if A2A's additional states are to be represented faithfully:

- Adding `SUBMITTED` would require a new initial state and transition path (`SUBMITTED -> WORKING`).
- Adding `AUTH_REQUIRED` would require a new interrupted state and transition path (`WORKING -> AUTH_REQUIRED -> WORKING`).
- These additions are backward-compatible: existing 5-state tasks would simply never enter the new states.

For MVP A2A support, the existing 5-state model is sufficient. `rejected`, `auth_required`, and `unknown` map to `failed` with descriptive error metadata. Extension can be deferred until A2A transport is actually implemented and the additional states provide operational value.

**Layer 3: ACP Client (`acp_dispatch.py` + `agent_providers/`) -- New provider or different connection model.**

This is the only layer that changes. Two integration paths:

| Approach | Description | Effort | Risk |
|---|---|---|---|
| **A2AProvider + HTTP dispatch loop** | New provider returns connection info instead of `ProcessSpec`. New dispatch function handles HTTP/SSE communication. | High (new dispatch loop, HTTP client, Agent Card handling) | Medium (proven pattern in A2A SDKs) |
| **A2AProvider + subprocess wrapper** | Provider launches A2A agent as subprocess, wraps HTTP communication internally. Returns `ProcessSpec` with port info in `session_meta`. | Medium (reuse existing subprocess lifecycle) | High (port management, lifecycle complexity) |
| **Wait for stdio transport** | No implementation. Monitor Issue #1074 and adopt when A2A natively supports stdio. | None | Low (but indefinite timeline) |

### 6. Recommendation

**A2A is not feasible today as a dispatch transport layer.** The reasons are:

1. **HTTP requirement is structural, not incidental.** A2A's design assumes network-boundary communication between autonomous agents. Stdio transport (Issue #1074) is under TSC review but not on the v0.3 roadmap and has received substantive pushback on architectural grounds.

2. **ProcessSpec does not fit the A2A model.** The `prepare_process()` -> `ProcessSpec` interface assumes subprocess spawning with stdio communication. A2A requires HTTP client/server with Agent Card discovery. Adapting the interface is possible but introduces significant complexity for a transport that no one in our ecosystem currently uses.

3. **No operational benefit today.** Both Gemini CLI and Claude Code communicate via ACP over stdio. A2A transport would serve remote/cloud agents, which is not a current use case for our local development dispatch framework.

**Revisit when:**

- A2A adds stdio transport (Issue #1074 merged and released in at least one official SDK), OR
- Gemini CLI natively bridges A2A over local transport (e.g., `--a2a` flag that handles HTTP lifecycle internally), OR
- Our dispatch framework needs to communicate with remote agents that expose A2A endpoints

**Preparedness:**

The `AgentProvider` ABC already supports adding new providers at Layer 3 without modifying Layers 1 or 2. When the time comes, an `A2AProvider` can be implemented alongside `GeminiProvider` and `ClaudeProvider`. The task state mapping (5-state to 9-state) is documented in this study and in ADR [[2026-02-07-dispatch-a2a-convergence]]. The task engine's state extension path is backward-compatible.

## External References

- [A2A Protocol Specification](https://a2a-protocol.org/latest/specification/)
- [A2A Roadmap](https://a2a-protocol.org/latest/roadmap/)
- [A2A GitHub: Issue #1074 (Stdio Transport)](https://github.com/a2aproject/A2A/issues/1074)
- [A2A GitHub Repository](https://github.com/a2aproject/A2A)
- [Linux Foundation A2A Project Launch](https://www.linuxfoundation.org/press/linux-foundation-launches-the-agent2agent-protocol-project-to-enable-secure-intelligent-communication-between-ai-agents)
- [Google Cloud A2A Donation](https://developers.googleblog.com/en/google-cloud-donates-a2a-to-linux-foundation/)
- [Gemini CLI RFC #7822: A2A Development-Tool Extension](https://github.com/google-gemini/gemini-cli/discussions/7822)
- [Gemini CLI PR #3079: A2A Client Support](https://github.com/google-gemini/gemini-cli/pull/3079)
- [Gemini CLI Issue #10482: A2A Server Integration](https://github.com/google-gemini/gemini-cli/issues/10482)
- [Gemini CLI v0.28.0-preview Changelog](https://geminicli.com/docs/changelogs/preview/)

## Internal References

- `agent_providers/base.py`: `AgentProvider` ABC, `ProcessSpec` dataclass, `resolve_includes()`
- `task_engine.py`: `TaskStatus` enum (5-state), `DispatchTask`, `_VALID_TRANSITIONS`
- `acp_dispatch.py:503-752`: `run_dispatch()` ACP session loop
- `mcp_dispatch.py`: MCP server (Layer 1 interface)
- [[2026-02-07-gemini-a2a-alignment-report]]: Cross-stream gap analysis (sections 2, 5, 6, 7)

---
tags: ["#research", "#a2a-protocol"]
related:
  - "[[2026-02-07-a2a-protocol-reference.md]]"
  - "[[2026-02-07-protocol-architecture.md]]"
  - "[[2026-02-07-multi-agent-orchestration-survey.md]]"
  - "[[2026-02-07-frontier-landscape.md]]"
  - "[[2026-02-07-protocol-review.md]]"
date: 2026-02-07
---

# A2A Protocol Compliance Brief

**Scope:** Full analysis of the A2A (Agent-to-Agent) Protocol specification against our dispatch architecture (`mcp_dispatch.py`, `task_engine.py`). Covers core concepts, state machine comparison, unimplemented features, protocol patterns for our gaps, and Agent Card vs MCP Resource gap analysis.

---

## 1. A2A Core Concepts

The A2A Protocol is an open standard created by Google (April 2025), donated to the Linux Foundation (June 2025). Version 0.3.x with 150+ supporting organizations. It enables communication between AI agents built on diverse frameworks, operating at the **Agent-to-Agent** layer of the three-protocol stack:

| Layer | Protocol | Boundary |
|---|---|---|
| Client-to-Agent | ACP (Zed) | Human <-> Agent |
| Agent-to-Tool | MCP (Anthropic) | Agent <-> Tool/Resource |
| **Agent-to-Agent** | **A2A (Google/LF)** | **Agent <-> Agent** |

Transport: HTTP(S), JSON-RPC 2.0, SSE, gRPC. Core principles: built on existing web standards, enterprise-ready (auth, security, tracing), asynchronous (native long-running task support), opaque execution (agents collaborate without exposing internals).

### 1.1 Agent Cards (Discovery)

Agent Cards are self-describing manifests served at `/.well-known/agent-card.json`. They enable dynamic discovery and capability negotiation between agents that have never interacted before.

**Key fields (from AgentCard protobuf):**

| Field | Purpose |
|---|---|
| `name`, `description`, `version` | Human-readable identity |
| `supported_interfaces` | URL, protocol binding (JSONRPC/GRPC/HTTP+JSON), protocol version |
| `capabilities` | Flags: `streaming`, `push_notifications`, `extended_agent_card` |
| `security_schemes` | API keys, HTTP auth, OAuth 2.0, OpenID Connect, mTLS |
| `security_requirements` | Which schemes are required for access |
| `default_input_modes` / `default_output_modes` | MIME types the agent accepts/produces |
| `skills` | Array of `AgentSkill` objects describing atomic capabilities |
| `icon_url` | Visual identity |
| `signatures` | Cryptographic signing for card integrity |

**AgentSkill structure:** Each skill has `id`, `name`, `description`, `tags`, `examples`, `input_modes`, `output_modes`, and `security_requirements`. This enables skill-level routing -- a client can discover which agent handles "currency conversion" vs "flight booking" by searching skill tags.

**Discovery methods (4):**

1. Well-Known URI (recommended): `GET https://{domain}/.well-known/agent-card.json`
2. Curated Registries: Central repositories queried by skill/tags/capabilities
3. Direct Configuration: Hardcoded URLs for tightly coupled systems
4. Extended Agent Card: Authenticated endpoint at `GET /extendedAgentCard` -- reveals private skills/capabilities after authentication

**Example Agent Card:**

```json
{
  "name": "Currency Agent",
  "description": "Helps with exchange rates",
  "url": "http://localhost:10000/",
  "version": "1.0.0",
  "defaultInputModes": ["text/plain"],
  "defaultOutputModes": ["text/plain"],
  "capabilities": { "streaming": true, "pushNotifications": true },
  "skills": [{
    "id": "convert_currency",
    "name": "Currency Exchange",
    "description": "Exchange rate lookups",
    "tags": ["currency"],
    "examples": ["What is USD to EUR?"]
  }],
  "supportedInterfaces": [{
    "url": "http://localhost:10000/",
    "protocolBinding": "JSONRPC",
    "protocolVersion": "0.3"
  }]
}
```

### 1.2 Task Lifecycle (9-state)

A2A defines a rigorous 9-state task lifecycle for tracking the full arc of delegated work:

| State | Category | Description |
|---|---|---|
| `submitted` | Active | Task created, server acknowledged receipt |
| `working` | Active | Actively being processed by the agent |
| `input_required` | Interrupted | Agent needs more info from the client to proceed |
| `auth_required` | Interrupted | Authentication/authorization needed before proceeding |
| `completed` | Terminal | Finished successfully, artifacts available |
| `failed` | Terminal | Finished with an error |
| `canceled` | Terminal | Terminated prematurely by client request |
| `rejected` | Terminal | Agent declined to perform the task |
| `unknown` | Terminal | Catch-all for undefined states |

**State transition diagram:**

```
submitted --> working --> input_required --> working (resumed) --> completed
                    \                   /
                     --> failed / canceled / rejected / auth_required
```

**Immutability rule:** Once terminal, a task cannot restart. New work for the same conceptual goal creates a new task in the same `contextId`.

### 1.3 Messages

Messages are interaction turns between agents, carrying typed content:

```protobuf
message Message {
  string message_id = 1;              // Unique per message
  string context_id = 2;              // Groups related interactions across tasks
  string task_id = 3;                 // Associated task
  Role role = 4;                      // USER or AGENT
  repeated Part parts = 5;            // Content containers (multi-part)
  google.protobuf.Struct metadata = 6;
  repeated string extensions = 7;
  repeated string reference_task_ids = 8;  // Cross-task relationships
}
```

Key design: `context_id` groups all tasks belonging to the same logical workflow. `reference_task_ids` enables explicit dependency links between tasks -- e.g., "Book hotel" references "Book flight" task.

### 1.4 Artifacts

Artifacts are named, described outputs produced by a completed task. They represent the formal transfer medium for results:

```protobuf
message Artifact {
  string artifact_id = 1;
  string name = 3;
  string description = 4;
  repeated Part parts = 5;            // Typed content
  google.protobuf.Struct metadata = 6;
  repeated string extensions = 7;
}
```

Artifacts can be streamed incrementally via `TaskArtifactUpdateEvent` with `append` and `last_chunk` flags, enabling progressive delivery of large outputs.

### 1.5 Parts (Content Containers)

Parts are the polymorphic content unit used in both Messages and Artifacts:

```protobuf
message Part {
  oneof content {
    string text = 1;                  // Plain text
    bytes raw = 2;                    // Binary data (images, files)
    string url = 3;                   // URL reference
    google.protobuf.Value data = 4;   // Structured JSON
  }
  google.protobuf.Struct metadata = 5;
  string filename = 6;
  string media_type = 7;
}
```

This enables a single message or artifact to contain mixed content -- e.g., a code snippet (text), a diagram (binary/url), and a structured report (JSON data) together.

### 1.6 Streaming (SSE)

A2A supports real-time streaming via `POST /message:stream` returning `Content-Type: text/event-stream`:

```
Client                              Server
  |-- POST /message:stream -------->|
  |<-- SSE: Task (submitted) ------|
  |<-- SSE: StatusUpdate (working) |
  |<-- SSE: ArtifactUpdate --------|
  |<-- SSE: StatusUpdate (complete)|
  |<-- Stream closed ---------------|
```

**StreamResponse** is a union type:

```protobuf
message StreamResponse {
  oneof payload {
    Task task = 1;
    Message message = 2;
    TaskStatusUpdateEvent status_update = 3;
    TaskArtifactUpdateEvent artifact_update = 4;
  }
}
```

Resubscription supported via `GET /tasks/{id}:subscribe` if connection drops.

### 1.7 Service Definition (11 RPCs)

| RPC | Method | Purpose |
|---|---|---|
| `SendMessage` | `POST /message:send` | Initiate interaction, returns Task or Message |
| `SendStreamingMessage` | `POST /message:stream` | Initiate with SSE streaming |
| `GetTask` | `GET /tasks/{id}` | Poll task status |
| `ListTasks` | `GET /tasks` | List tasks by context, status, pagination |
| `CancelTask` | `POST /tasks/{id}:cancel` | Request task cancellation |
| `SubscribeToTask` | SSE | Real-time status/artifact updates |
| `CreateTaskPushNotificationConfig` | POST | Register webhook for async notifications |
| `GetTaskPushNotificationConfig` | GET | Read push config |
| `ListTaskPushNotificationConfig` | GET | List all push configs |
| `DeleteTaskPushNotificationConfig` | DELETE | Remove push config |
| `GetExtendedAgentCard` | GET | Authenticated discovery |

### 1.8 Agent Response Patterns

A2A servers can operate in three response modes:

1. **Message-only**: Stateless, wrapping LLM calls. Returns `Message` directly, no task tracking.
2. **Task-generating**: Always returns `Task` objects. Full lifecycle tracking.
3. **Hybrid**: `Message` for initial negotiation, then `Task` for tracked work.

---

## 2. State Machine Comparison: A2A (9-state) vs Our 5-state

### 2.1 Our Internal State Machine

From `task_engine.py`, our `TaskStatus` enum defines 5 states:

```python
class TaskStatus(str, Enum):
    WORKING = "working"
    INPUT_REQUIRED = "input_required"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
```

**Valid transitions (from `_VALID_TRANSITIONS`):**

| From State | Allowed Transitions |
|---|---|
| `working` | `input_required`, `completed`, `failed`, `cancelled` |
| `input_required` | `working`, `completed`, `failed`, `cancelled` |
| `completed` | (none -- terminal) |
| `failed` | (none -- terminal) |
| `cancelled` | (none -- terminal) |

### 2.2 Mapping Table

| A2A State | Our State | Status | Rationale |
|---|---|---|---|
| `submitted` | (skipped) | **Rejected** | Our `create_task()` puts tasks directly into `working`. For local subprocess dispatch, the acknowledgment-before-processing phase is unnecessary. A2A needs `submitted` because the server may queue work asynchronously across a network. |
| `working` | `working` | **Adopted** | Direct equivalent. Active processing. |
| `input_required` | `input_required` | **Adopted** | State exists in our engine with correct bidirectional transitions (`working` <-> `input_required`). However, the actual interactive turn-taking flow is **not yet implemented** in `mcp_dispatch.py`. |
| `auth_required` | (skipped) | **Rejected** | Our sub-agents operate in a trusted local context with implicit authorization. No inter-organizational auth negotiation needed for subprocess dispatch. Relevant if/when we expose agents as A2A services. |
| `completed` | `completed` | **Adopted** | Terminal success state. |
| `failed` | `failed` | **Adopted** | Terminal error state. |
| `canceled` | `cancelled` | **Adopted** | Terminal cancellation state. Note spelling difference (A2A: `canceled`, ours: `cancelled`). |
| `rejected` | (skipped) | **Rejected** | For local dispatch, agent selection happens before task creation. If an agent cannot handle a task, it fails -- there is no pre-execution negotiation phase where rejection makes sense. A2A needs `rejected` for scenarios where a remote agent inspects the request and declines. |
| `unknown` | (skipped) | **Rejected** | Our system uses deterministic error handling. An `unknown` state would mask bugs rather than surface them. |

### 2.3 Transition Fidelity Assessment

**Correct alignments:**

- Terminal immutability: both A2A and our engine prevent transitions from terminal states.
- `input_required` <-> `working` bidirectional: A2A supports this, and our engine explicitly allows it via `_VALID_TRANSITIONS`.

**Gaps:**

- A2A allows `input_required` -> `completed` (agent resolves the need internally). Our engine also allows this, which is correct.
- A2A's `submitted` -> `working` transition is implicit in our `create_task()`. No data loss, but we cannot represent "queued but not yet started" state.

### 2.4 Our Additional Feature: Lock Release on Terminal Transitions

Our `TaskEngine` integrates advisory lock release on terminal state transitions (via `_release_lock()`). This is an implementation concern absent from A2A's pure state machine spec. A2A does not define workspace coordination because agents are self-contained services. Our lock integration is a pragmatic extension for shared-filesystem environments.

---

## 3. Unimplemented A2A Features for Collaborative Multi-Agent Workflows

### 3.1 Interactive `input_required` Flow (HIGH PRIORITY)

**A2A spec:** When a task enters `input_required`, the server returns a `Task` with a `Message` describing what information is needed. The client sends a follow-up `SendMessage` with the same `task_id` and `context_id`, resuming the task. The task transitions back to `working`.

**Multi-turn example:**

```
Turn 1: Client sends ambiguous query
  POST /message:send "How much is 100 USD?"
  -> Task { state: "input_required", message: "To which currency?" }

Turn 2: Client responds with same taskId + contextId
  POST /message:send { taskId: "task-1", contextId: "ctx-1", message: "in GBP" }
  -> Task { state: "completed", artifacts: [{ text: "79.23 GBP" }] }
```

**Our gap:** `task_engine.py` supports the state transitions (`working` <-> `input_required`), but `mcp_dispatch.py`'s `_run_dispatch_background()` treats dispatch as fire-and-forget. There is no mechanism for the team lead to:

1. Detect that a sub-agent is requesting input
2. Provide additional context to a paused task
3. Resume the sub-agent with the supplied input

**What would be needed:**

- A `resume_task(task_id, additional_input)` MCP tool
- The ACP dispatch client needs to support pausing on `input_required` and waiting for resume signals
- An `asyncio.Event` or queue per task for the team lead to inject follow-up messages

### 3.2 Streaming (SSE) for Real-Time Updates (MEDIUM PRIORITY)

**A2A spec:** `SendStreamingMessage` returns an SSE stream with `TaskStatusUpdateEvent` and `TaskArtifactUpdateEvent` events. The client receives incremental progress without polling.

**Our gap:** `mcp_dispatch.py` offers only `get_task_status` for polling. The team lead must repeatedly call this tool to check progress. There is no mechanism for push-based updates.

**What would be needed:**

- MCP does not natively support server-to-client push (tools are request-response). However, we could:
  - Implement a `subscribe_task(task_id)` tool that long-polls or uses MCP's notification mechanism
  - Capture ACP `session/update` streaming events from the sub-agent and forward them as structured progress updates in the task engine

### 3.3 Push Notifications (LOW PRIORITY)

**A2A spec:** Webhook-based async delivery. Client registers a `PushNotificationConfig` with a URL, session token, and authentication info. Server POSTs `StreamResponse` events to the webhook. Security: JWT + JWKS, HMAC, mTLS.

**Our gap:** Entirely absent. Our dispatch is local-process, so push notifications add complexity without immediate benefit.

**When relevant:** If/when sub-agents become remote A2A services or we integrate with external agent systems, push notifications would replace polling for inter-service communication.

### 3.4 Multi-Part Messages and Artifacts (MEDIUM PRIORITY)

**A2A spec:** Messages and Artifacts contain `repeated Part` fields, where each Part can be text, binary, URL, or structured JSON, with `filename` and `media_type` metadata.

**Our gap:** `_run_dispatch_background()` captures the sub-agent's response as a single text string (`response_text`). The result dict stores this as `"summary"` (truncated to 500 chars) and `"response"` (full text). The `"artifacts"` field is always an empty list:

```python
result = {
    "taskId": task_id,
    "status": "completed",
    "summary": (response_text or "")[:500],
    "response": response_text or "",
    "artifacts": [],  # Always empty
}
```

**What would be needed:**

- Parse sub-agent output for structured results (files written, JSON reports, etc.)
- Populate the `artifacts` list with typed entries matching A2A's Part schema
- Define an artifact manifest convention so sub-agents can formally declare their outputs

### 3.5 Context ID for Workflow Grouping (MEDIUM PRIORITY)

**A2A spec:** `context_id` groups all tasks belonging to a single logical workflow. Multiple tasks can share a `context_id`, enabling parallel follow-ups and historical tracking.

**Our gap:** `DispatchTask` has no `context_id` field. Each dispatch is independent. The team lead cannot query "all tasks related to the current feature implementation."

**What would be needed:**

- Add `context_id: str` to `DispatchTask`
- Accept optional `context_id` in `dispatch_agent()`
- Add `list_tasks(context_id=...)` filtering to `TaskEngine`

### 3.6 Cross-Task References (`reference_task_ids`) (LOW PRIORITY)

**A2A spec:** Messages include `reference_task_ids` to express dependencies between tasks. Example: "Book hotel" task references "Book flight" task because the hotel dates depend on flight arrival.

**Our gap:** No mechanism for expressing inter-task dependencies at the dispatch level. Claude Code's native `TaskCreate` has `blockedBy`, but our dispatch `TaskEngine` does not.

---

## 4. A2A Patterns for Our Gaps

### 4.1 Interactive Turn-Taking

**Current behavior:** Sub-agent dispatch is one-shot. The team lead provides all context upfront, the sub-agent executes, and returns a final result.

**A2A pattern:** `SendMessage` -> Task `input_required` -> `SendMessage` (follow-up) -> Task `working` -> Task `completed`. The `context_id` persists across turns, and the `task_id` is reused.

**Application to our system:**

```
Team Lead -> dispatch_agent("adr-researcher", "Analyze X")
  -> Task { status: "input_required", message: "Which aspect of X? Security, performance, or architecture?" }

Team Lead -> resume_task(task_id, "Focus on security implications")
  -> Task { status: "working" }
  -> Task { status: "completed", artifacts: [...] }
```

**Implementation sketch:**

1. Add `resume_task(task_id: str, input: str)` MCP tool
2. In `_run_dispatch_background()`, detect when the ACP sub-agent sends `input_required` signals
3. Park the background coroutine on an `asyncio.Queue` per task
4. When `resume_task` is called, push the input onto the queue
5. The background coroutine receives the input, sends a follow-up ACP prompt, and resumes

### 4.2 Agent-to-Agent Relay

**Current behavior:** The team lead dispatches to a single sub-agent. If that sub-agent needs help from another agent, there is no mechanism for it to delegate further.

**A2A pattern:** Any A2A agent can be both client and server. Agent A delegates to Agent B, which delegates to Agent C. Each leg uses the full A2A task lifecycle. `reference_task_ids` link the chain.

**Application to our system:** A sub-agent dispatched via `acp_dispatch.py` could itself use MCP tools (including `dispatch_agent`) to spawn further sub-agents. This is theoretically possible today since the ACP sub-agent has access to MCP servers, but:

- There is no formal mechanism for nested dispatch
- Lock contention would need to be managed (inner agent's locks vs outer agent's locks)
- The team lead has no visibility into the sub-delegation chain

**Recommendation:** Before enabling relay, implement context_id grouping so that nested dispatches share a workflow context and the team lead can track the full delegation tree.

### 4.3 Artifact Exchange

**Current behavior:** Sub-agents write files to `.docs/` by convention. The team lead reads them after dispatch completes. There is no formal artifact manifest.

**A2A pattern:** The `Artifact` type with named, typed `Part`s provides a formal contract. Artifacts are attached to the `Task` object and can be streamed incrementally.

**Application to our system:**

```python
# Current: flat text result
result = {
    "response": response_text,
    "artifacts": [],
}

# Enhanced: A2A-inspired artifacts
result = {
    "response": response_text,
    "artifacts": [
        {
            "artifact_id": "art-001",
            "name": "compliance-brief",
            "description": "A2A Protocol Compliance Brief",
            "parts": [
                {
                    "type": "text",
                    "media_type": "text/markdown",
                    "filename": ".docs/research/2026-02-07-a2a-protocol-compliance-brief.md",
                }
            ],
        }
    ],
}
```

**Implementation sketch:**

1. Define an artifact detection convention: sub-agents that write files emit a structured manifest (JSON) at the end of their output listing files created/modified
2. Parse the manifest in `_run_dispatch_background()` and populate the `artifacts` list
3. Include file paths, media types, and descriptions in each artifact entry

### 4.4 Parallel Follow-Up Tasks

**A2A pattern:** Multiple concurrent tasks within the same `context_id`, with cross-references:

```
Task 1: Book flight to Helsinki
Task 2: Based on Task 1 -> Book hotel (via referenceTaskIds)
Task 3: Based on Task 1 -> Book snowmobile activity
Task 4: Based on Task 2 -> Add spa reservation
```

**Application:** The team lead could dispatch multiple sub-agents simultaneously for independent research tracks, all sharing a `context_id`, then correlate their results. This is partially possible today (multiple `dispatch_agent` calls), but lacks:

- Shared context grouping
- Explicit dependency tracking
- Aggregate status queries ("are all tasks in context X completed?")

---

## 5. Agent Card vs MCP Resource: Comparison and Gap Analysis

### 5.1 Feature-by-Feature Comparison

| Dimension | A2A Agent Card | Our `agents://` MCP Resource |
|---|---|---|
| **Purpose** | Universal agent discovery, capability negotiation, security handshake | Internal sub-agent metadata for local dispatch |
| **Format** | Protobuf-defined schema, served as JSON over HTTPS | JSON dict generated from Markdown frontmatter |
| **Serving mechanism** | `GET /.well-known/agent-card.json` (HTTP endpoint) | `resources/read` MCP RPC via `mcp_dispatch.py` |
| **Identity** | `name`, `description`, `version`, `icon_url` | `name` (filename-derived), `description` |
| **Skills/Capabilities** | `skills[]` with per-skill `id`, `name`, `description`, `tags`, `examples`, `input_modes`, `output_modes` | `tools[]` (simple string list) |
| **Capability flags** | Explicit: `streaming`, `push_notifications`, `extended_agent_card` | None -- capabilities implicit |
| **Security** | `security_schemes` + `security_requirements` (OAuth 2.0, API keys, mTLS, OpenID Connect) | None -- implicit trust |
| **I/O modes** | `default_input_modes`, `default_output_modes` (MIME types) | None |
| **Interface bindings** | `supported_interfaces[]` with URL, protocol binding, version | None -- single dispatch mechanism |
| **Tier/Model** | Not in spec (could be in metadata) | `tier`, `default_model` (frontmatter fields) |
| **Permission mode** | Not in spec (security schemes cover this) | `default_mode` ("read-write" / "read-only") |
| **Cryptographic integrity** | `signatures[]` for card signing | None |
| **Extended discovery** | `GetExtendedAgentCard` RPC for authenticated access | None |
| **Dynamic refresh** | Not specified (HTTP caching) | File-watcher polls every 5s, emits `resources/list_changed` |

### 5.2 Gap Analysis

**What we have that A2A does not:**

- **Tier/model metadata**: Our frontmatter captures `tier` (LOW/MEDIUM/HIGH) and `default_model`, which are operational concerns A2A leaves to implementation.
- **Permission mode**: Our `default_mode` field is a workspace-safety concept absent from A2A (which assumes agents are self-contained).
- **File-based hot reload**: Our file-watcher detects agent definition changes and emits MCP notifications. A2A has no live-update mechanism.

**What A2A has that we lack:**

- **Skill-level routing**: A2A skills have `tags` and `examples` enabling semantic matching ("which agent handles currency conversion?"). Our `tools` list is flat strings.
- **Security negotiation**: A2A's security scheme discovery enables zero-trust agent interactions. We assume full trust.
- **Interface multiplexity**: A2A agents can expose multiple interfaces (JSONRPC + gRPC + HTTP+JSON). We have a single dispatch path.
- **Extended Agent Card**: Authenticated discovery of private capabilities. We expose everything or nothing.
- **Cryptographic signing**: A2A Agent Cards can be signed for integrity verification. We have no integrity guarantees on agent definitions.

### 5.3 Convergence Path

To evolve our MCP resources toward A2A Agent Card compatibility:

1. **Enrich skill metadata** (near-term): Replace the flat `tools` list with structured skill objects containing `id`, `description`, `tags`, `examples`. This enables better agent selection by the team lead.

2. **Add capability flags** (near-term): Expose whether an agent supports streaming, multi-turn interaction, artifact output, etc. Currently implicit.

3. **Define I/O modes** (medium-term): Specify what input formats an agent accepts and what output formats it produces. Currently agents are assumed to accept/produce plain text.

4. **Security scheme preparation** (long-term): If agents become remote A2A services, Agent Cards with security schemes would replace the current implicit-trust model.

---

## 6. Implementation Priority Summary

| Feature | Priority | Effort | A2A Alignment | Impact on Our Architecture |
|---|---|---|---|---|
| Artifact manifests in task results | HIGH | Low | Artifacts + Parts | Eliminates file-convention dependency |
| `context_id` for workflow grouping | HIGH | Low | Core concept | Enables multi-task correlation |
| `resume_task` for `input_required` | HIGH | Medium | Multi-turn flow | Unlocks interactive sub-agent work |
| Enriched skill metadata in agent resources | MEDIUM | Low | AgentSkill | Better agent selection |
| Streaming progress updates | MEDIUM | Medium | SSE / StreamResponse | Real-time visibility into sub-agent work |
| Cross-task references | LOW | Low | `reference_task_ids` | Dependency tracking for parallel dispatch |
| Push notifications | LOW | High | Webhook-based delivery | Only relevant for remote agents |
| Full A2A Agent Card serving | LOW | Medium | Agent Card spec | Only relevant for external federation |

---

## 7. Architectural Recommendation

The central tension identified in the protocol architecture document remains:

> Our dispatcher needs the **process control** of ACP (spawn subprocess, stdio, filesystem, terminals) combined with the **interaction semantics** of A2A (task delegation, structured results, status tracking, discovery).

The recommended path is **Option 4 from the architecture doc: Hybrid**. Keep ACP for transport (subprocess management) and layer A2A semantics on top:

1. **Adopt A2A data models** (Artifact, Part, AgentSkill) as internal conventions, even without HTTP transport
2. **Add `context_id`** to `DispatchTask` for workflow grouping
3. **Implement `input_required` flow** via an async resume mechanism
4. **Enrich agent metadata** toward Agent Card compatibility
5. **Keep our 5-state machine** -- it is a correct, intentional subset of A2A's 9 states for our local-dispatch use case

This approach gains A2A's interaction semantics without the infrastructure overhead of standing up HTTP agent services, and positions us for future A2A adoption if agents become remote services.

---

## Sources

- A2A Protocol Specification: <https://a2a-protocol.org/latest/specification/>
- A2A Protocol Definitions: <https://a2a-protocol.org/latest/definitions/>
- A2A Key Concepts: <https://a2a-protocol.org/latest/topics/key-concepts/>
- A2A Streaming and Async: <https://a2a-protocol.org/latest/topics/streaming-and-async/>
- A2A Agent Discovery: <https://a2a-protocol.org/latest/topics/agent-discovery/>
- A2A Python SDK: <https://a2a-protocol.org/latest/sdk/python/api/>
- A2A GitHub: <https://github.com/a2aproject/A2A>
- A2A Samples: <https://github.com/a2aproject/a2a-samples>
- Internal: `.rules/scripts/mcp_dispatch.py` (Phase 4 MCP dispatch server)
- Internal: `.rules/scripts/task_engine.py` (5-state task engine)
- Internal: `.rules/scripts/docs/2026-02-07-a2a-protocol-reference.md`
- Internal: `.rules/scripts/docs/2026-02-07-protocol-architecture.md`
- Internal: `.rules/scripts/docs/2026-02-07-protocol-review.md`

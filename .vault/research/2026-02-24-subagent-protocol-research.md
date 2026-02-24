---
tags:
  - "#research"
  - "#subagent-protocol"
date: "2026-02-24"
related:
  - "[[2026-02-24-subagent-protocol-adr]]"
---

# `subagent-protocol` research: Subagent Spawning and Debugging Protocol Stack

Research into the optimal protocol stack for spawning, managing, and debugging
subagents (child agents delegated work by an orchestrator). Compares the current
Zed ACP approach against A2A over localhost HTTP, with focus on debuggability.

## Findings

### 1. Current Architecture — Zed ACP over stdio

The vaultspec subagent layer currently uses Zed's `agent-client-protocol`
package. The architecture is:

```
Orchestrator
 └─ SubagentClient (acp.Client protocol over stdio)
     └─ spawn_agent_process() → child subprocess
         └─ GeminiACPBridge / ClaudeACPBridge (acp.Agent protocol)
```

**Key files and sizes:**

- `protocol/acp/client.py` — 683 lines, SubagentClient (ACP Client impl)
- `protocol/acp/gemini_bridge.py` — ~800 lines, Gemini CLI wrapper
- `protocol/acp/claude_bridge.py` — ~800 lines, Claude SDK wrapper
- `protocol/providers/base.py` — 367 lines, AgentProvider ABC, ProcessSpec

**ACP SDK internals (agent-client-protocol 0.8.1):**

- `interfaces.py` — Agent + Client Protocol classes
  - `Agent`: initialize → new_session → prompt → cancel (session-oriented)
  - `Client`: session_update, request_permission, file I/O, terminal management
- `stdio.py` — spawn_agent_process, spawn_client_process (pipe lifecycle)
- `connection.py` — JSON-RPC 2.0 framing over stdin/stdout
- `schema.py` — Protocol message types (generated from spec)

**Pain points:**

- Editor-oriented vocabulary (sessions, modes, terminals) doesn't map cleanly
  to orchestrator↔subagent semantics
- Bridges are monolithic (~800 lines each) coupling protocol, process, and I/O
- No inspection tools — messages flow through opaque pipes
- No standard debugging/tracing — must add custom logging
- Testing requires spawning real subprocesses (or building complex mocks)

### 2. A2A SDK Architecture (a2a-sdk)

The official A2A Python SDK provides a clean separation:

**Server-side (subagent):**

- `AgentExecutor` ABC — just implement `execute()` and `cancel()`
  - Receives `RequestContext` (message, task_id, context_id)
  - Publishes events to `EventQueue` (Task → working → completed)
- `DefaultRequestHandler` — wires executor to request handling
- `InMemoryTaskStore` — task state management (or SQL stores)
- `A2AStarletteApplication` — HTTP server (JSON-RPC + REST endpoints)
- `AgentCard` — capability advertisement at `/.well-known/agent-card.json`

**Client-side (orchestrator):**

- `Client` ABC — send_message, get_task, cancel_task, resubscribe, get_card
- `ClientConfig` — streaming, polling, transport preferences
- `ClientFactory` — auto-discovers agent via AgentCard, picks best transport
- Transports: JSON-RPC over HTTP, REST, gRPC (all HTTP-based, no stdio)

**Minimal agent pattern (from TCK + helloworld samples):**

```python
class MyAgentExecutor(AgentExecutor):
    async def execute(self, context: RequestContext, event_queue: EventQueue):
        result = await self.agent.invoke(context.get_user_input())
        await event_queue.enqueue_event(new_agent_text_message(result))

    async def cancel(self, context, event_queue):
        # publish TaskState.canceled
        ...

# Server setup (~20 lines)
handler = DefaultRequestHandler(
    agent_executor=MyAgentExecutor(),
    task_store=InMemoryTaskStore(),
)
app = A2AStarletteApplication(agent_card=card, http_handler=handler).build()
uvicorn.run(app, host="127.0.0.1", port=port)
```

### 3. Debugging Tooling Comparison

| Tool | A2A | ACP (Zed) |
|---|---|---|
| **A2A Inspector** | ✅ Web UI, JSON-RPC console, spec compliance | ❌ N/A |
| **OpenTelemetry** | ✅ Built-in `[telemetry]` extra | ❌ Manual logging |
| **TCK conformance** | ✅ Automated spec validation | ❌ N/A |
| **respx HTTP mocking** | ✅ Mock entire transport in tests | ❌ Must mock stdio |
| **Message inspection** | ✅ HTTP → any proxy/debugger | ❌ Opaque pipe |
| **Agent Card discovery** | ✅ Standard capability negotiation | ❌ Hardcoded |

### 4. Transport Trade-offs

| Property | ACP stdio | A2A localhost HTTP |
|---|---|---|
| Process lifecycle | Pipe = process | Need graceful shutdown |
| Port management | None | Ephemeral ports (`--port 0`) |
| Latency | ~0.1ms | ~1ms (localhost TCP) |
| Debuggability | Opaque | Full HTTP tooling |
| Standard compliance | Zed-specific | Linux Foundation standard |
| Testing | Complex stdio mocks | `respx` / `httpx` mocks |
| Future portability | Local only | Can deploy remotely |

### 5. Critical Finding — A2A has no stdio transport

The A2A protocol does not define a stdio transport binding. All official
transports are HTTP-based (JSON-RPC, REST, gRPC). For subprocess-spawned
subagents, this means:

1. The child process must start an HTTP server (uvicorn) on localhost
2. The parent connects via `httpx` to `http://localhost:{port}`
3. This adds ~1ms latency and port management overhead
4. But unlocks the entire HTTP debugging ecosystem

Community discussion suggests a stdio transport may be added in future A2A
versions, but for now HTTP is the only option.

### 6. Key Differences — Session vs Task Model

**ACP (session-oriented):**

- `initialize` → `new_session` → `prompt` → `session_update` streams
- Stateful sessions with mode switching, model switching
- File I/O and terminal management built into protocol
- Single prompt → streaming chunks → response

**A2A (task-oriented):**

- `message/send` → Task with lifecycle (submitted → working → completed)
- Stateless per-request, task store for persistence
- No file/terminal primitives — handled by the agent internally
- Message → Task updates → Artifacts

The task model is cleaner for our use case: we submit a prompt, get back
a result with possible streaming updates. We don't need session resumption,
mode switching, or editor terminal management.

### 7. Candidate Approaches

**Option A — A2A over localhost HTTP (recommended)**

Spawn subagent as HTTP server on ephemeral port. Full debugging, standard
protocol, clean test mocking with `respx`.

**Option B — Keep ACP stdio, refactor code**

Extract protocol logic from bridges, add structured logging. Less invasive
but no Inspector, no TCK, no community tools.

**Option C — A2A message semantics over custom stdio transport**

Write thin JSON-RPC layer using A2A types but over stdio pipes. Best of
both worlds but non-standard, no Inspector support, maintenance burden.

### 8. Critical Gap — A2A Server Lifecycle Management

**The A2A protocol and SDK have no subprocess spawning or process management
story.** All official samples and reference implementations assume agents are
independently running services that the orchestrator connects to by URL.

**Reference implementation analysis:**

- `samples/python/hosts/multiagent/host_agent.py` — takes
  `remote_agent_addresses: list[str]` (hardcoded URLs), resolves `AgentCard`
  per address, wraps each in `RemoteAgentConnections(client_factory, card)`.
  No spawning, no shutdown, no health checks.
- `samples/python/hosts/a2a_multiagent_host/__main__.py` — bootstraps a
  _single_ long-lived A2A server via `uvicorn.run(app, host, port)`. No
  dynamic port allocation, no lifecycle management beyond uvicorn's built-in
  signal handling.
- `samples/python/hosts/multiagent/remote_agent_connection.py` — wraps
  `ClientFactory.create(card)` to get a `Client`, tracks pending tasks.
  57 lines total. No reconnection, no process lifecycle awareness.
- `demo/ui/service/server/adk_host_manager.py` (638 lines) — manages
  conversations, tasks, and events, but treats agents as external services
  registered by URL via `register_agent(url)`. No subprocess management.

**Current vaultspec process lifecycle (for comparison):**

`orchestration/subagent.py` → `run_subagent()` (618 lines) manages:

1. Provider resolution + `ProcessSpec` construction
2. `spawn_agent_process()` — creates subprocess with stdio pipes
3. Stderr drain task (prevents buffer deadlock)
4. ACP handshake with 30s timeout (`initialize` + `new_session`)
5. Interactive conversation loop
6. Graceful shutdown: `cancel()` → `kill_process_tree()` → `wait(5s)` →
   forced `kill()` → transport cleanup → `gc.collect()`
7. Temp file cleanup from `ProcessSpec.cleanup_paths`

**Two server lifecycle models for A2A migration:**

| Model | Description | Trade-offs |
|---|---|---|
| **Per-task ephemeral** | Spawn server before each task, kill after | Clean isolation, no port leaks, mirrors current ACP pattern. Adds ~200ms startup overhead per task (uvicorn boot). |
| **Long-lived per-provider** | Spawn server once, reuse for all tasks | Lower latency after first task, matches A2A reference patterns. Requires health checks, reconnection logic, graceful shutdown coordination. |

**Recommended: Per-task ephemeral** — matches the current `run_subagent`
lifecycle model, avoids stale connection bugs, and keeps the process
supervisor simple. The ~200ms uvicorn startup is negligible compared to the
multi-second LLM response times. Server reuse can be added later as an
optimisation if needed.

**Key implementation concern:** With ACP stdio, pipe closure = process death
(the OS enforces this). With A2A HTTP, the server subprocess can become
orphaned if the parent crashes without cleanup. The new process supervisor
must handle:

- Readiness probe (poll `GET /` or `GET /.well-known/agent-card.json` until
  200)
- Watchdog/heartbeat (detect parent death — e.g. via PID file or pipe trick)
- `kill_process_tree()` on Windows (same as current ACP cleanup)
- Port conflict avoidance (bind to port 0, report actual port to parent)

---
tags:
  - "#research"
  - "#protocol"
date: "2026-02-20"
related:
  - "[[2026-02-07-a2a-research]]"
  - "[[2026-02-15-a2a-adr]]"
  - "[[2026-02-15-cross-agent-bidirectional-communication]]"
---
# A2A Team Protocol Research: Multi-Agent Team Coordination Patterns

Research into how the A2A protocol (v0.3.x, a2a-sdk v0.3.22) supports multi-agent
team coordination -- the foundation for vaultspec's planned "a2a-team" feature.
Examines contextId semantics, parallel task chains, security model, and gaps
requiring custom orchestration.

## Findings

### 1. contextId as Team Session

**How it works:** A `contextId` is an opaque string identifier that logically groups
multiple related `Task` and `Message` objects, providing continuity across a series
of interactions. When a client sends a message without a `contextId`, the server
generates one. Subsequent messages from the client that include the same `contextId`
signal continuation within the same conversation or session.

**Can it serve as a team session ID?** Yes, with caveats:

- **Affirmative:** contextId already groups multiple concurrent tasks toward a common
  goal. The spec explicitly states it enables "collaboration towards a common goal or
  a shared contextual session across multiple, potentially concurrent tasks." A team
  coordinator could generate a single contextId and pass it to all agent servers
  participating in a team session. Each agent server would then associate its tasks
  with this shared session.

- **Limits:**
  - contextId is **per-server scoped** -- each A2A server manages its own task store.
    Two different agent servers receiving the same contextId will independently create
    their own tasks. The coordinator must stitch results together.
  - No built-in **expiration or TTL** is mandated by the spec. Servers MAY implement
    expiration policies, but this is implementation-defined.
  - No **cross-server context synchronization** -- the protocol does not define how
    two servers should share or reconcile context state. The contextId is purely a
    hint for the server's internal state management.
  - contextId carries no **team membership** semantics. It doesn't encode which agents
    belong to a team or what roles they play.

**Recommendation:** Use contextId as the *transport-level session ID* for a team, but
build a `TeamSession` abstraction on top that tracks membership, roles, and
cross-agent state. The contextId gets passed to all A2A servers, but the coordinator
owns the team lifecycle.

### 2. Parallel Agent Chains via referenceTaskIds

**How it works:** The `Message` object contains a `reference_task_ids` field
(repeated string). Clients SHOULD use this to explicitly reference related tasks.
Agents SHOULD use referenced tasks to understand context and intent.

**Can Agent A and Agent B both reference a team task?**

Yes. The pattern works as follows:

```
Team Coordinator creates Task-0 (seed task)
  |
  +-- Dispatches to Agent A: referenceTaskIds = ["task-0-id"]
  |     -> Agent A creates Task-A, processes, returns result
  |
  +-- Dispatches to Agent B: referenceTaskIds = ["task-0-id"]
  |     -> Agent B creates Task-B, processes, returns result
  |
  v
Coordinator collects Task-A and Task-B results, aggregates
```

This enables fan-out/fan-in coordination. The spec's sailboat booking example
demonstrates exactly this: Task 2 (book hotel) and Task 3 (book snowmobile) both
reference Task 1 (book flight) and execute in parallel within the same contextId.

**Limitation:** referenceTaskIds are opaque hints. The server has no obligation to
fetch or understand the referenced task's content -- it merely knows a relationship
exists. Cross-server task references (Agent A referencing a task on Agent B's server)
require the coordinator to include the referenced task's output in the message body,
since Agent A's server cannot directly query Agent B's task store.

### 3. Native Team Concepts in A2A v0.3.x

**The short answer: A2A has NO built-in team, broadcast, or multi-agent orchestration
concepts.** The protocol is fundamentally a client-server bilateral communication
protocol between one client and one server.

What exists:

- **contextId:** Groups tasks into sessions (see above).
- **referenceTaskIds:** Creates task dependency graphs (see above).
- **tenant field:** An optional namespace isolation parameter present in most request
  types (SendMessage, GetTask, ListTasks, CancelTask, push notifications,
  GetExtendedAgentCard). It isolates operations within shared infrastructure but
  carries no team semantics. Use case: a SaaS A2A platform serving multiple
  organizations. For vaultspec's team use, `tenant` could encode a team ID, but this
  is a creative repurposing, not the intended use.
- **ListTasks with contextId filter:** `ListTasksRequest` supports filtering by
  `contextId`, which allows a coordinator to enumerate all tasks in a team session.
  This is useful for monitoring and result aggregation.
- **Multiple concurrent streams:** "An agent MAY serve multiple concurrent streams to
  one or more clients for the same task." This supports multiple observers of the same
  task, relevant for team dashboards or leader monitoring.

What does NOT exist:

- No team formation or dissolution protocol.
- No agent roster or membership management.
- No broadcast or multicast messaging.
- No role-based access within a team context.
- No consensus or voting mechanisms.
- No shared workspace or artifact aggregation.
- No agent-to-agent direct communication (always client-to-server).

### 4. Team Lifecycle Mapping to A2A States

| Team Event | A2A Mapping | Notes |
|---|---|---|
| Team forms | Coordinator generates contextId | No protocol event; purely coordinator logic |
| Agent assigned | Coordinator discovers agent via Agent Card | GET `/.well-known/agent-card.json` |
| Agent working | Task transitions to `working` | Per-agent task state; coordinator polls or streams |
| Agent idle | No A2A state for "idle" | Coordinator must track agent availability separately |
| Agent reports result | Task transitions to `completed` | Artifacts contain the result |
| Agent needs input | Task transitions to `input_required` | Coordinator must provide follow-up |
| Agent fails | Task transitions to `failed` | Error message in status |
| Team dissolves | No protocol event | Coordinator stops dispatching; tasks reach terminal states |

**Key gap:** A2A has no "idle" or "available" state. The protocol is task-centric, not
agent-centric. Between tasks, the agent simply has no active task -- there is no
heartbeat or presence mechanism.

### 5. A2A Security Model

**Agent Card declares security requirements:**

```json
{
  "securitySchemes": {
    "apiKey": { "type": "apiKey", "in": "header", "name": "X-API-Key" },
    "oauth2": { "type": "oauth2", "flows": { "clientCredentials": { ... } } }
  },
  "security": [{ "apiKey": [] }]
}
```

**Supported authentication schemes:**

- `APIKeySecurityScheme` -- API key in header, query, or cookie
- `HTTPAuthSecurityScheme` -- Basic or Bearer token
- `OAuth2SecurityScheme` -- Authorization code, client credentials, device code flows
- `OpenIdConnectSecurityScheme` -- OIDC discovery URL
- `MutualTlsSecurityScheme` -- mTLS certificate pinning

**How access levels between agents work:**

- **Public vs. Extended Agent Cards:** An unauthenticated client sees the public card.
  After authenticating, it can request `GET /extendedAgentCard` to receive a more
  detailed card with additional skills and capabilities. This provides tiered access:
  trusted agents see more capabilities.
- **Per-request authentication:** Every SendMessage, GetTask, etc. requires valid
  credentials matching the card's security requirements. The server verifies before
  processing.
- **No per-message authorization:** A2A does not define fine-grained permissions like
  "Agent X can send task type Y but not Z." Authorization is binary: authenticated or
  not. Role-based restrictions must be implemented in the executor logic.

**For vaultspec team coordination:**

The coordinator (Claude Code session) would authenticate to each agent server. Since
we control both client and server, the simplest approach is API key exchange during
team formation. For local development (localhost), security can be relaxed. For
production, OAuth2 client credentials or mTLS between agents is appropriate.

### 6. Current Implementation State

**Existing code in `.vaultspec/lib/src/protocol/a2a/`:**

| File | Status | Purpose |
|---|---|---|
| `__init__.py` | Implemented | Package init with docstring |
| `state_map.py` | Implemented | Bidirectional TaskEngine<->A2A state mapping (6+9 states) |
| `agent_card.py` | Implemented | Agent Card generation from agent definitions |
| `discovery.py` | Implemented | Gemini CLI agent discovery file generation |
| `server.py` | Implemented | `create_app()` -- wraps executor+card into Starlette ASGI app |
| `executors/base.py` | Implemented | Re-exports sandbox logic from `protocol.sandbox` |
| `executors/claude_executor.py` | Implemented | ClaudeA2AExecutor -- claude-agent-sdk wrapper with timeouts, DI |
| `executors/gemini_executor.py` | Implemented | GeminiA2AExecutor -- delegates to `run_subagent()` via ACP |

**Test coverage:**

| Test File | Tests | Scope |
|---|---|---|
| `test_unit_a2a.py` | 10 | State mapping, agent card, executor logic (no network) |
| `test_integration_a2a.py` | 10 | In-process HTTP via ASGI transport (no LLM) |
| `test_e2e_a2a.py` | 6 | Real LLM bidirectional (requires Claude+Gemini CLIs) |
| `test_french_novel_relay.py` | 2 | 3-turn collaborative relay (mock + live) |
| `test_claude_executor.py` | exists | Claude executor unit tests |
| `test_gemini_executor.py` | exists | Gemini executor unit tests |
| `test_discovery.py` | exists | Discovery file generation tests |
| `test_agent_card.py` | exists | Agent card generation tests |

**ADR:** `.vault/adr/2026-02-15-a2a-adr.md` -- Proposed status, covers full 6-phase
implementation plan. Phases 1-4 (foundation, server, Claude executor, Gemini executor)
are implemented. Phase 5 (gold standard bidirectional) has E2E tests. Phase 6 (Gemini
CLI discovery) has implementation but needs further testing.

**What the French novel relay test demonstrates:**

The `test_french_novel_relay.py` is the closest existing example to team coordination.
It chains 3 agents sequentially (Claude begins -> Gemini continues -> Claude finishes),
passing output from one turn as input to the next. This validates:
- Multi-agent message chaining via A2A
- Task ID independence across agents
- Content continuity through the chain
- Both mock (deterministic `StoryRelayExecutor`) and live (real LLM) variants

However, this is strictly **sequential** coordination, not the parallel fan-out/fan-in
pattern needed for team operations.

### 7. TeamCoordinator Pattern Design

A Claude Code session acting as team lead would use the following pattern:

```
                       +--> A2A Server (Agent A) -- ClaudeA2AExecutor
                       |        localhost:10010
Claude Code Session    |
  (Team Coordinator)   +--> A2A Server (Agent B) -- GeminiA2AExecutor
  Uses A2AClient       |        localhost:10011
  httpx-based          |
                       +--> A2A Server (Agent C) -- ClaudeA2AExecutor
                                localhost:10012
```

**TeamCoordinator responsibilities:**

```python
class TeamCoordinator:
    """Orchestrates a team of A2A agent servers."""

    def __init__(self):
        self.context_id: str          # Shared team session
        self.agents: dict[str, A2AClient]  # name -> client
        self.tasks: dict[str, Task]   # task_id -> A2A Task
        self.results: dict[str, str]  # agent_name -> result text

    async def form_team(self, agent_urls: list[str]):
        """Discover agents and create team session."""
        self.context_id = str(uuid4())
        for url in agent_urls:
            resolver = A2ACardResolver(httpx_client, base_url=url)
            card = await resolver.get_agent_card()
            client = A2AClient(httpx_client, agent_card=card)
            self.agents[card.name] = client

    async def dispatch_parallel(self, assignments: dict[str, str]):
        """Fan-out: dispatch tasks to multiple agents concurrently."""
        # All messages share contextId + reference the seed task
        coros = []
        for agent_name, task_text in assignments.items():
            msg = SendMessageRequest(
                params=MessageSendParams(
                    message=Message(
                        role=Role.user,
                        context_id=self.context_id,
                        reference_task_ids=list(self.tasks.keys()),
                        parts=[Part(root=TextPart(text=task_text))],
                    )
                )
            )
            coros.append(self._dispatch_one(agent_name, msg))
        results = await asyncio.gather(*coros, return_exceptions=True)
        return results

    async def collect_results(self) -> dict[str, str]:
        """Fan-in: aggregate completed task results."""
        return self.results

    async def dissolve_team(self):
        """Clean up: close HTTP clients."""
        for client in self.agents.values():
            await client.close()
```

**Key design decisions:**

- **contextId is coordinator-generated** and shared across all agent servers.
- **referenceTaskIds** link dependent tasks: if Agent B's work depends on Agent A's
  result, the dispatch to Agent B includes Agent A's task ID in `referenceTaskIds`
  AND includes Agent A's output in the message body (since Agent B's server cannot
  query Agent A's server directly).
- **Fan-out uses `asyncio.gather()`** for concurrent dispatch.
- **Fan-in uses polling or streaming.** For blocking tasks, the coordinator awaits
  each `send_message()` call. For non-blocking (long-running) tasks, the coordinator
  polls `get_task()` or subscribes to SSE streams.
- **Error handling:** If any agent fails, the coordinator decides whether to retry,
  reassign, or abort the team. A2A's terminal state immutability means failed tasks
  stay failed -- a new task must be created for retry.

### 8. Gap Analysis: What's Missing for Team Coordination

| Gap | Severity | Workaround |
|---|---|---|
| No team formation protocol | High | Build `TeamCoordinator` abstraction on top of A2A |
| No agent presence/heartbeat | Medium | Coordinator pings agent cards periodically; track liveness |
| No broadcast messaging | Medium | Coordinator loops over agents, sending individually |
| No cross-server task visibility | High | Coordinator aggregates via `ListTasks` per server; include referenced output in message body |
| No role-based authorization | Low | Implement in executor logic; different executors for different roles |
| No shared artifact store | Medium | Coordinator extracts artifacts from completed tasks and re-injects into subsequent dispatches |
| No agent "idle" state | Low | Track at coordinator level: agent is idle when it has no active tasks |
| No consensus/voting | Low | Not needed for current use case; coordinator makes decisions |
| referenceTaskIds are cross-server opaque | Medium | Coordinator must relay referenced task content in message body |
| InMemoryTaskStore is per-process | Medium | Fine for local dev; production needs persistent store (SQL backends available in a2a-sdk extras) |

**What a2a-sdk v0.3.22 already provides:**

- `A2AClient` with `send_message()`, `get_task()`, `cancel_task()`, streaming support
- `A2ACardResolver` for agent discovery
- `DefaultRequestHandler` + `InMemoryTaskStore` for server-side task management
- `AgentExecutor` abstract base class for custom agent logic
- `TaskUpdater` for emitting A2A lifecycle events
- Pydantic models for all protocol types (Task, Message, Part, AgentCard, etc.)
- SQL-backed task stores (`sqlite`, `mysql`, `postgres` extras) for persistent storage

**What we need to build:**

- `TeamCoordinator` class: team formation, parallel dispatch, result aggregation
- `TeamSession` model: contextId, agent roster, roles, state
- Agent liveness monitoring (periodic Agent Card checks or custom health endpoint)
- Cross-agent result relay: extracting artifacts and including in subsequent messages
- Integration with vaultspec's existing `TaskEngine` for team-level task tracking
- CLI command: `subagent.py team-serve` to start multiple A2A servers for a team
- Test fixtures: `TeamCoordinatorFixture` with mock agents for CI

## Summary

A2A v0.3.x provides strong primitives for team coordination -- contextId for session
grouping, referenceTaskIds for dependency graphs, concurrent task support, and a rich
client/server SDK -- but it is fundamentally a bilateral (client-server) protocol with
no native team concepts. The "team" abstraction must be built on top: a
`TeamCoordinator` that owns the team lifecycle, dispatches to individual A2A servers,
and aggregates results. The existing vaultspec A2A implementation (Phase 1-5 complete)
provides the foundation: executors, server wiring, state mapping, and bidirectional
E2E tests. The next step is the `TeamCoordinator` layer.

## Sources

- [A2A Protocol Specification](https://a2a-protocol.org/latest/specification/)
- [Life of a Task - A2A Protocol](https://a2a-protocol.org/latest/topics/life-of-a-task/)
- [A2A Protocol Key Concepts](https://a2a-protocol.org/latest/topics/key-concepts/)
- [a2a-sdk v0.3.22 on PyPI](https://pypi.org/project/a2a-sdk/)
- [O'Reilly: Designing Collaborative Multi-Agent Systems with A2A](https://www.oreilly.com/radar/designing-collaborative-multi-agent-systems-with-the-a2a-protocol/)
- [IBM: What Is Agent2Agent Protocol?](https://www.ibm.com/think/topics/agent2agent-protocol)
- [A2A Python SDK GitHub](https://github.com/a2aproject/a2a-python)
- [A2A Samples GitHub](https://github.com/a2aproject/a2a-samples)

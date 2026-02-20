---
tags:
  - "#research"
  - "#protocol"
date: "2026-02-20"
related:
  - "[[2026-02-20-a2a-team-claude-code-tools-research]]"
  - "[[2026-02-20-a2a-team-protocol-research]]"
  - "[[2026-02-20-a2a-team-gemini-research]]"
  - "[[2026-02-15-a2a-adr]]"
  - "[[2026-02-07-a2a-research]]"
---

# `a2a-team` Feasibility Synthesis

**Verdict: Technically feasible. Foundation is largely in place.**

Three parallel investigations covered: (1) Claude Code Team API & vaultspec CLI gaps,
(2) A2A protocol multi-agent team coordination patterns, (3) Gemini native A2A/ACP
team support. This document synthesizes findings into a unified feasibility assessment
and architecture design.

---

## Feasibility: HIGH

The building blocks for `a2a-team` are either already implemented or straightforwardly
constructible from existing primitives. The A2A ADR (Phases 1–5) is **complete**: both
executors (Claude, Gemini), the HTTP server, state mapping, agent card generation,
discovery file generation, and a full test suite including a sequential multi-agent
relay (`test_french_novel_relay.py`). The missing layer is **team-level coordination**
on top of these individual agent primitives.

---

## What Exists Today

| Component | Status | Location |
|---|---|---|
| `ClaudeA2AExecutor` | Implemented | `protocol/a2a/executors/claude_executor.py` |
| `GeminiA2AExecutor` | Implemented | `protocol/a2a/executors/gemini_executor.py` |
| `create_app()` A2A server | Implemented | `protocol/a2a/server.py` |
| State mapping (TaskEngine↔A2A) | Implemented | `protocol/a2a/state_map.py` |
| Agent Card generation | Implemented | `protocol/a2a/agent_card.py` |
| Gemini CLI discovery files | Implemented | `protocol/a2a/discovery.py` |
| `a2a-serve` CLI subcommand | Implemented | `lib/scripts/subagent.py` |
| Unit + integration + E2E tests | Implemented | `protocol/a2a/tests/` |
| French novel relay test | Implemented | `protocol/a2a/tests/test_french_novel_relay.py` |

**The gap is not the bilateral A2A plumbing — it's the N-agent team orchestration layer.**

---

## Architecture Design

### Three-Layer Stack

```
┌─────────────────────────────────────────────────────────────────┐
│  TEAM LAYER (NEW)                                               │
│  TeamCoordinator — owns team lifecycle, parallel dispatch,      │
│  result aggregation, liveness monitoring                         │
│                                                                  │
│  TeamSession: contextId, agent roster, roles, collective state  │
│                                                                  │
│  vaultspec team CLI: create/add-member/assign/broadcast/dissolve │
└────────────────────────────┬────────────────────────────────────┘
                             │ uses
┌────────────────────────────▼────────────────────────────────────┐
│  A2A LAYER (EXISTS — Phase 1-5 complete)                        │
│  ClaudeA2AExecutor / GeminiA2AExecutor                          │
│  A2AStarletteApplication (HTTP server)                          │
│  A2AClient + A2ACardResolver (discovery, dispatch)              │
│  InMemoryTaskStore / SQL-backed options                         │
└────────────────────────────┬────────────────────────────────────┘
                             │ uses
┌────────────────────────────▼────────────────────────────────────┐
│  ACP/MCP LAYER (EXISTS — unchanged)                             │
│  run_subagent() → GeminiProvider / ClaudeProvider               │
│  vs-subagent-mcp (5 tools)                                      │
└─────────────────────────────────────────────────────────────────┘
```

### TeamCoordinator (Core New Class)

```
TeamCoordinator
  .form_team(agent_urls)         — discover agents via Agent Cards, share contextId
  .dispatch_parallel(assignments) — fan-out: asyncio.gather across A2AClient.send_message()
  .collect_results()             — fan-in: poll get_task() or SSE subscribe
  .relay_output(src, dst, text)  — cross-agent result relay (inject into next message body)
  .ping_agents()                 — liveness: GET /.well-known/agent.json periodically
  .dissolve_team()               — cancel active tasks, close HTTP clients
```

### Agent Roles in a Team

| Role | Implementation | Permission |
|---|---|---|
| Team lead (Claude Code session) | Coordinator; uses A2AClient | read-write |
| Claude member | ClaudeA2AExecutor on its own port | read-only or read-write |
| Gemini member | GeminiA2AExecutor on its own port | read-only (subprocess) |
| Observer | Subscribes to SSE streams | read-only |

---

## Key Design Decisions

### 1. contextId = Team Session ID

The coordinator generates a single `contextId` (UUID) before dispatching any tasks.
All messages to all agent servers carry this contextId. Per-server, contextId groups
tasks into a session. The coordinator owns the team registry — agent servers are
unaware of each other.

### 2. Gemini Participates as A2A Server Target

Gemini CLI cannot run as a native persistent A2A server (RFC #7822 — unimplemented).
Instead: `GeminiA2AExecutor` wraps Gemini as an A2A executor; each inbound A2A task
spawns a fresh Gemini CLI subprocess via ACP. The A2A server is persistent; only the
Gemini subprocess restarts per task. This is already the pattern in Phase 4.

Gemini CAN act as an A2A *client* via the experimental `@a2a` tool (PR #3079, requires
`experimental.enableAgents: true` in settings.json). This enables Gemini to
sub-delegate tasks during its own execution.

### 3. A2A Has No Native Team Concepts — Build on Top

A2A is fundamentally bilateral (one client, one server). There is no broadcast,
roster, or team formation protocol. What A2A provides as team primitives:

- **contextId** — groups tasks into a session (used as team session ID)
- **referenceTaskIds** — links dependent tasks (for sequential chains)
- **tenant** — namespace isolation (creative team ID use)
- **ListTasks(contextId=...)** — enumerate all tasks in a session

Everything else (fan-out, fan-in, idle tracking, broadcast, coordinated shutdown)
must be built in `TeamCoordinator`.

### 4. No A2A Idle State — Track at Coordinator Level

A2A is task-centric: between tasks, an agent simply has no active task. The coordinator
tracks availability by: (a) inferring idle from absence of active tasks, (b) periodic
Agent Card pings as a liveness check. No heartbeat protocol is needed.

### 5. Cross-Agent Result Relay

Agent B's server cannot query Agent A's task store directly. When B's task depends on
A's result: the coordinator fetches A's completed task artifacts, extracts the text,
and injects it into B's incoming message body alongside `referenceTaskIds: [A's task id]`.

### 6. Security

- **Local dev**: unauthenticated localhost connections (A2A spec permits this)
- **Production**: API key in `X-API-Key` header declared in Agent Card `securitySchemes`
- **Gemini's @a2a tool**: no outbound auth config yet (experimental limitation)
- **vaultspec team auth**: coordinator holds per-agent API keys issued at team formation

---

## What Needs to Be Built (Gap Analysis)

| Component | Complexity | Depends On |
|---|---|---|
| `TeamCoordinator` class | Medium | a2a-sdk A2AClient (exists) |
| `TeamSession` model | Low | nothing new |
| Team-level `TaskEngine` extension | Medium | existing TaskEngine |
| In-process message bus (asyncio.Queue per agent) | Low | nothing new |
| Agent liveness monitor | Low | A2ACardResolver (exists) |
| `team` CLI commands (create/add/assign/broadcast/dissolve) | Medium | TeamCoordinator |
| MCP tools: `create_team`, `add_member`, `get_team_status`, `dissolve_team` | Medium | TeamCoordinator |
| Cross-agent result relay helper | Low | A2AClient.get_task() (exists) |
| Test fixtures: `TeamCoordinatorFixture` with mock agents | Low | EchoExecutor (exists) |
| CI markers: `@pytest.mark.team` | Trivial | pytest config |

**NOT needed:**

- Google ADK (parallel framework, overlapping concerns)
- New LLM providers (existing Claude + Gemini executors suffice)
- New transport protocols (HTTP/JSON-RPC via a2a-sdk covers it)
- Persistent task store beyond InMemoryTaskStore for local use (SQL extras available if needed)

---

## CLI Design

Proposed extensions to `subagent.py`:

```
subagent.py team-create --name <id> [--agents agent1:port1,agent2:port2]
subagent.py team-status --name <id>
subagent.py team-assign --name <id> --agent <agent> --task "<description>"
subagent.py team-broadcast --name <id> --message "<text>"
subagent.py team-dissolve --name <id>
```

Or as a separate `team.py` script following the same CLI conventions as `subagent.py`
and `vault.py` (all accept `--root`, type=Path, ROOT_DIR fallback).

MCP additions to `vs-subagent-mcp` (5 new tools):

```
create_team(name, agent_urls)        -> team_id
add_member(team_id, agent_url)       -> member_id
get_team_status(team_id)             -> TeamStatus
dissolve_team(team_id)               -> summary
send_team_message(team_id, content, recipient?) -> message_id
```

---

## Risks

| Risk | Severity | Mitigation |
|---|---|---|
| A2A spec changes before 1.0 | Low | Thin executor wrapper isolates; test suite catches regressions |
| Gemini subprocess latency per task | Medium | Accept for now; ACP resume possible future optimization |
| Port collisions in CI (multi-server) | Low | ASGI transport for integration tests (no real TCP) |
| asyncio complexity (N concurrent streams) | Medium | asyncio.gather + timeout guards |
| InMemoryTaskStore lost on restart | Low | SQL extras available; not needed for local teams |

---

## Recommended Next Steps

1. **ADR**: Document the `TeamCoordinator` + team CLI architectural decision.
2. **Plan**: Define implementation phases (Foundation → Coordinator → CLI → MCP tools → Tests).
3. **Execute Phase 1**: `TeamSession` model + `TeamCoordinator` skeleton with `form_team()` + `dispatch_parallel()`.
4. **Execute Phase 2**: `team-create` / `team-dissolve` CLI commands + basic integration test.
5. **Execute Phase 3**: MCP tools (`create_team`, `get_team_status`, `dissolve_team`).
6. **Execute Phase 4**: Full test suite with `TeamCoordinatorFixture` + mock agents.
7. **Review**: Code review via `vaultspec-review` before merge.

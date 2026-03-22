---
tags:
  - '#adr'
  - '#a2a'
date: '2026-02-24'
related:
  - '[[2026-02-24-a2a-adr]]'
  - '[[2026-02-24-subagent-protocol-research]]'
  - '[[2026-02-24-cli-protocols-research]]'
  - '[[2026-02-24-a2a-server-manager-adr]]'
---

<!-- DO NOT add 'Related:', 'tags:', 'date:', or other frontmatter fields
     outside the YAML frontmatter above -->

# `a2a` server: One A2A Server Per Agent — No Master Server | (**status:** `accepted`)

## Problem Statement

With the unified A2A protocol decided in
`[[2026-02-24-a2a-adr]]`, a server topology decision is
required: how are A2A servers deployed when the orchestrator needs to talk
to agents? One server handling all agents? One server per agent? A hybrid?

## Considerations

### Option A: One master server, multiple executor routes

A single HTTP server process hosts all executors. The orchestrator sends
tasks to different URL paths (e.g., `/gemini/tasks`, `/claude/tasks`).

- **Pro:** One process to manage, one port.
- **Con:** Crash in one executor takes down all agents. Complex routing.
  Shared state risks. Does not match A2A's model where each agent has its
  own agent card at `/.well-known/agent-card.json`.

### Option B: One server per agent (chosen)

Each agent gets its own process with its own HTTP server on an ephemeral
port. The orchestrator connects to each independently.

- **Pro:** Process isolation (one crash doesn't affect others). Clean
  lifecycle (kill process = done). Matches A2A's agent-card-per-server
  model. Simple — each server wraps exactly one executor.

- **Con:** Multiple processes. Port management. Slightly more resource
  usage.

### Option C: Pre-running persistent servers

Long-lived servers that persist across tasks. The orchestrator connects to
already-running servers.

- **Not chosen** — doesn't fit vaultspec's per-task invocation pattern.
  Each task is independent. The A2A reference implementations assume this
  model (see `[[2026-02-24-subagent-protocol-research]]` §8), but it adds
  complexity without benefit for our use case.

## Constraints

- Must work for both single subagent invocations (1 server) and multi-agent
  teams (N servers).

- Must work on Windows (process tree cleanup via `kill_process_tree()`).

- Startup overhead must be negligible relative to LLM response times.

## Implementation

Each agent — whether a solo subagent or a member of a team — gets its own
process running its own HTTP server on an ephemeral port. The orchestrator
is the A2A **client**. It is NOT a server.

### Single subagent

```text
Orchestrator (vaultspec — A2A CLIENT)
 │
 └─ spawn A2A Server on port 52341 (uvicorn + GeminiA2AExecutor)
      └─ handles tasks for this one Gemini agent
      └─ internally spawns gemini --experimental-acp subprocess
```

### Team of agents

```text
Orchestrator (vaultspec — A2A CLIENT)
 │
 ├─ spawn A2A Server on port 52341 (GeminiA2AExecutor)
 │    └─ Gemini code review agent
 │
 ├─ spawn A2A Server on port 52342 (ClaudeA2AExecutor)
 │    └─ Claude code review agent
 │
 └─ spawn A2A Server on port 52343 (ClaudeA2AExecutor)
      └─ Claude auditor/supervisor agent

 A2AClient connects to each server independently.
```

### Server lifecycle: per-task ephemeral

- **Spawned** when a subagent is invoked or a team member is started.
- **Killed** when the task completes, fails, or is cancelled.
- **~200ms** uvicorn startup is negligible vs LLM seconds.

## Rationale

1. **Isolation** — one agent crash cannot take down others.

1. **Simplicity** — each server wraps one executor, no routing logic.

1. **A2A conformance** — one agent card per server, per the spec.

1. **Lifecycle parity** — matches current ACP model where each
   `run_subagent()` spawns one process.

1. **Clean teardown** — kill process = kill server = done.

## Consequences

- **Positive:** Fault isolation, simple lifecycle, A2A-conformant agent
  card behavior, works uniformly for subagents and teams.

- **Negative:** Multiple processes per team. Port management complexity
  (mitigated by ephemeral OS-assigned ports). Slightly higher resource
  usage for large teams (acceptable given LLM-bound workloads).

---
tags:
  - "#adr"
  - "#a2a"
date: "2026-02-24"
related:
  - "[[2026-02-24-a2a-adr]]"
  - "[[2026-02-24-a2a-server-architecture-adr]]"
  - "[[2026-02-24-subagent-protocol-research]]"
  - "[[2026-02-24-cli-protocols-research]]"
---
<!-- DO NOT add 'Related:', 'tags:', 'date:', or other frontmatter fields
     outside the YAML frontmatter above -->

# `a2a` server lifecycle: Shared `ServerProcessManager` | (**status:** `accepted`)

## Problem Statement

With A2A requiring per-agent server processes, as
Something must manage the lifecycle of these processes: spawning,
readiness probing, port discovery, shutdown, and orphan prevention.
Two code paths currently need this capability:

- `orchestration/subagent.py` — spawns a single agent.
- `orchestration/team.py` — spawns multiple agents for team coordination.

Without a centralised solution, server lifecycle code will be duplicated
between these modules, recreating the fragmentation this rewrite eliminates.

## Considerations

### Option A: Inline lifecycle in each module

Each module (`subagent.py`, `team.py`) manages its own processes.

- **Con:** Duplicated spawn/readiness/shutdown logic. Every fix to process
  management (timeout tuning, port discovery edge cases, Windows cleanup)
  must be applied in two places. This is the **exact problem** the unified
  A2A protocol ADR was created to solve.

### Option B: Shared `ServerProcessManager` (chosen)

A single class owns all A2A server process lifecycle concerns. Both
`subagent.py` and `team.py` use the same instance.

- **Pro:** Zero duplication. One fix, one test, one place.
- **Pro:** Natural place for observability (active server listing, health).
- **Pro:** `shutdown_all()` for team cleanup.

### Option C: External process supervisor (systemd, supervisord)

- **Not chosen** — overkill for ephemeral per-task servers. Adds external
  dependency. Doesn't work cross-platform (Windows).

## Constraints

- A single subagent is a team of size 1. The same `ServerProcessManager`
  MUST handle both without special-casing.
- Must work on Windows (process tree cleanup via `kill_process_tree()`).
- Must prevent orphaned servers when the parent process crashes.

## Implementation

`ServerProcessManager` lives at `protocol/a2a/server_manager.py` (~200 LOC)
and provides the following API:

| Method | Purpose | Used by |
| ------ | ------- | ------- |
| `spawn(provider, config)` | Start A2A server subprocess | Both |
| `wait_ready(proc)` | Block until server is healthy | Both |
| `shutdown(proc)` | Graceful teardown of one server | Both |
| `shutdown_all()` | Teardown all managed servers | Teams |
| `list_active()` | Return active server metadata | Teams |

### Lifecycle responsibilities

1. **Spawn** — `asyncio.create_subprocess_exec()` with stderr pipe.
2. **Port discovery** — child writes `PORT={port}` to stdout after bind.
3. **Readiness probe** — poll `GET /.well-known/agent-card.json` with
   exponential backoff (50ms → 100ms → 200ms → ...) up to 30s timeout.
4. **Stderr drain** — background task prevents buffer deadlock.
5. **Shutdown** — `kill_process_tree(pid)` on Windows, `SIGTERM` →
   wait(5s) → `SIGKILL` on Unix.
6. **Orphan prevention** — child monitors parent PID; if parent dies,
   child calls `sys.exit()`. Background thread checking `os.getppid()`
   on Unix, or named pipe / job object on Windows.

### Integration points

- **`orchestration/subagent.py`** — `spawn()` → `wait_ready()` → A2A
  client interaction → `shutdown()`.
- **`orchestration/team.py`** — `spawn()` × N → `wait_ready()` × N →
  A2A coordination → `shutdown_all()`.
- **Both paths** share the same readiness probe, port discovery, stderr
  drain, and process cleanup logic.

## Rationale

1. **No duplication** — one component handles all server lifecycle.
2. **Fragmentation prevention** — duplicating process management between
   `subagent.py` and `team.py` would recreate the same class of bug the
   unified A2A rewrite eliminates.
3. **Centralised observability** — `list_active()` provides a single view
   of all running agent servers for monitoring and debugging.
4. **Clean team teardown** — `shutdown_all()` ensures no orphaned servers
   after team completion.

## Consequences

- **Positive:** Zero duplication of process lifecycle code. Single point
  of testing. Centralised health monitoring. Clean team teardown.
- **Negative:** `ServerProcessManager` is new critical infrastructure
  (~200 LOC) with no equivalent in A2A reference implementations. Must be
  thoroughly tested, especially orphan prevention on Windows. The A2A SDK
  provides no subprocess management (see
  `[[2026-02-24-subagent-protocol-research]]` §8).

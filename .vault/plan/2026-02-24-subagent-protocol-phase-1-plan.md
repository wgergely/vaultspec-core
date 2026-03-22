---
tags:
  - '#plan'
  - '#subagent-protocol'
date: '2026-02-24'
related:
  - '[[2026-02-24-subagent-protocol-research]]'
  - '[[2026-02-24-subagent-protocol-adr]]'
  - '[[2026-02-15-subagent-adr]]'
---

# `subagent-protocol` `phase-1` plan

Rewrite the vaultspec subagent spawning layer to use A2A over localhost HTTP,
replacing the current Zed ACP stdio approach. This plan covers Phase 1 —
establishing the Gemini provider on A2A, validating the pattern, then
migrating Claude.

## Proposed Changes

Per \[[2026-02-24-subagent-protocol-adr]\], the subagent layer shifts from
ACP stdio to A2A localhost HTTP. The A2A SDK provides `AgentExecutor`,
`DefaultRequestHandler`, `InMemoryTaskStore`, and `A2AStarletteApplication`
— drastically reducing bridge code.

The A2A reference implementations do NOT handle subprocess spawning (see
\[[2026-02-24-subagent-protocol-research]\] §8). Vaultspec must build a
`ServerProcessManager` — the critical new component that replaces ACP's
`spawn_agent_process` with HTTP-based process supervision.

Key changes:

1. New `ServerProcessManager` for spawning, health-checking, and tearing
   down A2A server subprocesses (per-task ephemeral model)

1. New A2A agent server modules for Gemini and Claude

1. New A2A client module replacing SubagentClient

1. Updated providers to spawn HTTP servers instead of ACP stdio processes

1. New tests using `respx` HTTP mocking

1. Removal of `python-a2a` from `tmp-ref/`

1. Retention of `agent-client-protocol` for editor integration (unchanged)

## Tasks

- Phase 1: Foundation + Gemini migration

  1. Remove `tmp-ref/python-a2a/` directory

  1. Create `protocol/a2a/server_manager.py` — `ServerProcessManager`
     class owning the full subprocess lifecycle:

     - `spawn(executable, args, env)` → `asyncio.create_subprocess_exec`

     - Port discovery via stdout (`PORT={port}` protocol)

     - `wait_ready(port, timeout=30)` — health check loop polling
       `GET /.well-known/agent-card.json` with exponential backoff

     - Stderr drain background task

     - `shutdown(proc)` — `kill_process_tree()` → wait(5s) → force kill

     - Orphan prevention watchdog (child monitors parent PID)

  1. Create `protocol/a2a/server.py` — shared A2A server bootstrap
     (AgentCard, DefaultRequestHandler, A2AStarletteApplication, uvicorn).
     Entry point: `python -m vaultspec.protocol.a2a.server --provider gemini --port 0`. Writes `PORT={actual_port}` to stdout after bind.

  1. Create `protocol/a2a/gemini_executor.py` — `AgentExecutor` wrapping
     Gemini CLI subprocess

  1. Create `protocol/a2a/client.py` — A2A client wrapper (replaces
     SubagentClient for A2A agents)

  1. Update `protocol/providers/gemini.py` — `prepare_process` returns
     A2A server ProcessSpec instead of ACP bridge

  1. Write tests for `server_manager.py` — spawn/ready/shutdown lifecycle

  1. Write tests for `gemini_executor.py` using `respx` HTTP mocking

  1. Write tests for `client.py` using `respx`

  1. Run existing `protocol/tests/test_providers.py` — ensure Gemini
     provider tests still pass with updated ProcessSpec

- Phase 2: Claude migration

  1. Create `protocol/a2a/claude_executor.py` — `AgentExecutor` wrapping
     Claude SDK

  1. Update `protocol/providers/claude.py` — A2A server ProcessSpec

  1. Write tests for `claude_executor.py` using `respx`

  1. Run existing `protocol/tests/test_providers.py` — ensure Claude
     provider tests still pass

- Phase 3: Cleanup + Integration

  1. Update `protocol/__init__.py` exports

  1. Deprecate / remove old ACP bridge files (claude_bridge.py,
     gemini_bridge.py, old client.py) — after validation

  1. Update `protocol/acp/tests/` — remove tests for deleted bridge code,
     keep SubagentClient tests that still apply to editor integration

  1. Integration test: spawn real A2A server + client roundtrip

  1. Add OpenTelemetry tracing configuration

## Parallelization

- Steps 1.3 and 1.4 can be developed in parallel (server bootstrap +
  executor)

- Steps 1.7, 1.8, and 1.9 can be written in parallel (independent test
  suites)

- Phase 2 is independent of Phase 1 cleanup (Phase 3)

- Phase 3 step 5 (OpenTelemetry) is independent of all other cleanup steps

## Verification

### Unit Tests

**Existing tests (must still pass):**

```bash

# Run from project root

uv run pytest src/vaultspec/protocol/tests/test_providers.py -v
```

This runs `TestGeminiProvider` and `TestClaudeProvider` — tests model
selection, ProcessSpec construction, system prompt ordering. These must pass
with updated ProcessSpec format.

```bash

# Run from project root

uv run pytest src/vaultspec/protocol/tests/ -v -k "not test_provider_auth"
```

Runs all protocol-level tests except auth (which requires network access).

**New tests (to be written):**

```bash

# Run ServerProcessManager lifecycle tests

uv run pytest src/vaultspec/protocol/a2a/tests/test_server_manager.py -v

# Run Gemini executor tests

uv run pytest src/vaultspec/protocol/a2a/tests/test_gemini_executor.py -v

# Run A2A client tests

uv run pytest src/vaultspec/protocol/a2a/tests/test_client.py -v
```

`test_server_manager.py` will validate:

- Spawn + port discovery (mock subprocess writing `PORT=12345` to stdout)
- Readiness probe retry logic (mock httpx returning 503 then 200)
- Shutdown cleanup (`kill_process_tree` called, process waited)
- Timeout handling (process fails to become ready within deadline)
- Orphan prevention (parent PID watchdog triggers exit)

`test_gemini_executor.py` and `test_client.py` will use `respx` to mock
HTTP transport — no subprocess spawning, no real API calls. Tests will
validate:

- AgentCard discovery (GET `/.well-known/agent-card.json`)
- Task submission (POST `message/send`)
- Streaming events (SSE `message/sendSubscribe`)
- Task cancellation
- Error handling (agent down, timeout, malformed response)

### Manual Verification

1. Start a standalone A2A Gemini agent server:

   ```bash
   uv run python -m vaultspec.protocol.a2a.server --provider gemini --port 8765
   ```

1. Point the A2A Inspector at `http://localhost:8765` — verify AgentCard
   renders, send a test prompt, observe JSON-RPC messages in debug console.

1. Use the test client:

   ```bash
   uv run python -m vaultspec.protocol.a2a.test_client --url http://localhost:8765
   ```

### Success Criteria

- All existing `test_providers.py` tests pass unchanged (or with minimal
  ProcessSpec format updates)

- `ServerProcessManager` tests cover spawn, readiness, shutdown, timeout,
  and orphan prevention

- New respx-based tests cover executor lifecycle, client transport, and
  error handling

- A2A Inspector can connect to and debug a running agent server

- No regression in existing editor integration (agent-client-protocol
  remains untouched)

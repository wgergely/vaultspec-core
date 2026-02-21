---
tags:
  - "#research"
  - "#claude-a2a-overhaul"
date: "2026-02-21"
related:
  - "[[2026-02-21-protocol-layer-audit-research]]"
  - "[[2026-02-21-claude-sdk-rate-limit-research]]"
  - "[[2026-02-21-claude-acp-bidirectional-reference]]"
  - "[[2026-02-20-a2a-team-adr]]"
  - "[[2026-02-21-claude-acp-bidirectional-adr]]"
---

# `claude-a2a-overhaul` research: Claude A2A Executor & Team Coordination

Synthesis of protocol audit, rate limit research, reference implementations
(`tmp-ref/a2a-python-sdk`, `tmp-ref/acp-claude-code`), and current
implementation analysis. This is the second of six protocol cases identified
in [[2026-02-21-claude-acp-bidirectional-adr]].

## Current State

**Baseline: 69/69 non-E2E tests pass. 1 E2E failure (rate_limit_event crash).**

### ClaudeA2AExecutor (`claude_executor.py`, 223 lines)

Single-shot A2A executor. Accepts DI via `client_factory` / `options_factory`.
Creates an SDK client per `execute()`, connects, queries, streams
`AssistantMessage` / `ResultMessage`, disconnects. Has cancel support via
`_active_clients` dict tracking.

**Issues identified:**

- **Rate limit crash (P0):** `MessageParseError` from `rate_limit_event` is
  caught and silently skipped via `logger.debug`. Stream may die without
  `ResultMessage`, handled by the `_finalised` fallback. However, the E2E test
  still fails because the stream sometimes terminates fatally.
- **No retry (P0):** Transient failures (rate limits, network blips) result in
  immediate task failure. No backoff or retry logic.
- **No session resume (P1):** Each `execute()` creates a fresh SDK client.
  The `session_id` from `ResultMessage` is never extracted or stored. Multi-turn
  conversations across A2A tasks in the same `context_id` are not possible.
- **Cancel is destructive (P1):** `cancel()` calls `interrupt()` + `disconnect()`.
  The SDK client is destroyed. Cannot resume after cancel.
- **No `AssistantMessage.error` checking (P1):** Executor only collects
  `TextBlock` content from `AssistantMessage.content`. The `.error` field
  (which can be `"rate_limit"`, `"authentication_failed"`, etc.) is ignored.
- **No streaming events (P2):** Only emits `working` → `completed/failed`.
  No intermediate `TaskStatusUpdateEvent` or `TaskArtifactUpdateEvent` during
  streaming. Rich A2A clients see no progress.
- **`_stream.__anext__()` pattern (P3):** Uses manual `__aiter__()`/`__anext__()`
  instead of `async for`. Works but is non-idiomatic and harder to read.

### TeamCoordinator (`orchestration/team.py`, 571 lines)

Functional multi-agent orchestration. Forms teams via agent card discovery,
dispatches tasks in parallel with `asyncio.gather`, relays output with
`reference_task_ids`, pings agents, dissolves with cleanup.

**Issues identified:**

- **No session-level continuity (P2):** Each `dispatch_parallel()` creates a
  new `SendMessageRequest`. The `context_id` is set to `team_id` (correct per
  ADR Decision 2) but there is no mechanism to send follow-up messages to an
  existing task. Tasks are fire-and-forget.
- **No streaming dispatch (P2):** Uses `client.send_message()` which waits for
  a complete response. The A2A SDK supports `send_message_streaming()` but it's
  not used. Long-running tasks block the coordinator.
- **Cancel propagation gap (P2):** `dissolve_team()` calls `cancel_task()` via
  A2A JSON-RPC, which reaches the server's `DefaultRequestHandler`. But the
  handler's cancel path may not propagate to the underlying executor's
  `_active_clients` if the task has already completed.

### A2A Server (`server.py`, 62 lines)

Thin wrapper around `A2AStarletteApplication`. Creates
`DefaultRequestHandler` + `InMemoryTaskStore`. Works correctly for single-shot
tasks. No issues identified beyond the executor-level problems above.

### Test Coverage

| Test File | Count | Status | Notes |
|-----------|-------|--------|-------|
| `test_unit_a2a.py` | 11 | Pass | State mapping, agent card, executors |
| `test_claude_executor.py` | 7 | Pass | DI-based unit tests |
| `test_gemini_executor.py` | 6 | Pass | DI-based unit tests |
| `test_integration_a2a.py` | 11 | Pass | In-process HTTP tests |
| `test_agent_card.py` | 5 | Pass | Card serialization |
| `test_discovery.py` | 5 | Pass | Agent discovery/settings |
| `test_e2e_a2a.py` | 8 | 7 pass, 1 fail | E2E: `test_claude_a2a_responds` |
| `test_french_novel_relay.py` | 1 | Skip | Requires both CLIs |
| `test_team.py` | 12 | Pass | Team coordination |

## Reference Implementation Analysis

### `a2a-python-sdk` (`tmp-ref/a2a-python-sdk`)

The official A2A Python SDK provides:

- **`BaseClient.send_message()`** with streaming/polling fallback: checks
  `card.capabilities.streaming`, uses SSE when available, falls back to
  polling with `ClientTaskManager` tracking.
- **`EventQueue`** with bounded backpressure: parent-child `tap()` pattern
  for fan-out, graceful `close()` with drain semantics.
- **`TaskUpdater`** convenience API: `start_work()`, `update_status()`,
  `add_artifact()`, `complete()`, `failed()`, `cancel()`. Already used by
  our executor.
- **Transport abstraction:** `RestTransport`, `GrpcTransport`,
  `JsonRpcTransport`. Our server uses the Starlette/JSON-RPC path.

Key pattern: the SDK client handles streaming transparently. Our
`TeamCoordinator` already uses `A2AClient` from this SDK but only calls
`send_message()` (non-streaming). Switching to streaming requires the
executor to publish intermediate events via `EventQueue`.

### `acp-claude-code` (`tmp-ref/acp-claude-code`)

TypeScript reference for ACP bridge patterns. Key patterns already extracted
in Phase 1 (per-session state, content accumulation, kind mapping). Relevant
to A2A executor:

- **Stateless query per turn:** Each `prompt()` runs a fresh `query()` with
  `resume` parameter. Adapted for Python SDK architecture (persistent
  `ClaudeSDKClient` with `connect()`/`disconnect()` lifecycle).
- **Non-destructive cancel:** `AbortController` per session, `interrupt()`
  not `disconnect()`.
- **Error as message chunk:** Errors emitted as content, stop reason always
  `"end_turn"` (never `"refusal"`).

### `a2a-educational` (`tmp-ref/a2a-educational`)

Multi-agent orchestration patterns:

- **Orchestrator with tool-based routing:** LLM decides which sub-agent to
  delegate to. Uses `ToolContext.state` for per-agent session tracking.
- **Lightweight `AgentConnector`:** Thin wrapper around `A2AClient` with
  `send_task()` method. Similar to our `TeamCoordinator._dispatch_one()`.
- **Session tracking per child agent:** Each child gets its own `session_id`
  in the orchestrator's state dict. Maps to our `context_id` approach.

## Key Findings

### Finding 1: Rate limit handling requires retry, not skip

Current code skips `MessageParseError` at debug level. The stream may die
without a `ResultMessage`, triggering the `_finalised` fallback which
either completes with collected text or fails with "Stream ended without
result". This is unreliable.

**Recommended:** Parse `exc.data` from `MessageParseError` to detect
`rate_limit_event`. Implement bounded retry loop (3 attempts, exponential
backoff). Only fail after retries exhausted.

### Finding 2: Session resume enables multi-turn A2A

`ResultMessage` carries `session_id`. Storing it per task context enables
reconnecting to the same conversation. For A2A, this means follow-up
messages in the same `context_id` can resume the Claude conversation.

**Recommended:** Store `session_id` from `ResultMessage` in a per-context
dict on the executor. Pass as `resume` parameter when creating a new
`ClaudeSDKClient` for the same `context_id`.

### Finding 3: Non-destructive cancel preserves session state

Current `cancel()` destroys the SDK client. If the user cancels mid-stream
and then sends a follow-up message, the executor must create a fresh session
with no history.

**Recommended:** Use `interrupt()` without `disconnect()`. Track cancel
state per task. Clear cancel state at start of next `execute()`.

### Finding 4: Streaming events improve observability

A2A spec supports `TaskStatusUpdateEvent` and `TaskArtifactUpdateEvent`
for streaming progress. Currently we only emit `working` at start and
`completed`/`failed` at end.

**Recommended:** Emit intermediate status updates during streaming:
- On each `AssistantMessage`: emit `TaskArtifactUpdateEvent` with
  accumulated text
- On `MessageParseError`: emit status update noting rate limit/retry
- On cancel detection: emit status update before canceling

### Finding 5: Phase 1 patterns should be shared

Phase 1 (ACP bridge) implemented per-session state, content accumulation,
tool kind mapping. These patterns are applicable to the A2A executor as
well. However, the A2A executor operates at a different level of abstraction
(A2A task model vs ACP session model), so direct code sharing may not be
appropriate. The patterns should be applied conceptually.

### Finding 6: Team coordinator streaming is a separate concern

The `TeamCoordinator` uses the A2A SDK's `send_message()` which returns
a complete response. Switching to `send_message_streaming()` requires
handling `ClientEvent` objects during dispatch. This is a meaningful
enhancement but orthogonal to the executor overhaul. Should be done after
the executor is fixed.

---
tags:
  - "#adr"
  - "#claude-a2a-overhaul"
date: "2026-02-21"
related:
  - "[[2026-02-21-claude-a2a-overhaul-research]]"
  - "[[2026-02-21-protocol-gap-analysis-research]]"
  - "[[2026-02-21-a2a-ref-impl-research]]"
  - "[[2026-02-21-a2a-layer-audit-research]]"
  - "[[2026-02-21-claude-sdk-rate-limit-research]]"
  - "[[2026-02-21-claude-acp-bidirectional-adr]]"
  - "[[2026-02-20-a2a-team-adr]]"
---

# `claude-a2a-overhaul` adr: `Claude A2A Executor & Team Coordination Overhaul` | (**status:** `accepted`)

## Problem Statement

The `ClaudeA2AExecutor` (`src/vaultspec/protocol/a2a/executors/claude_executor.py`) is a single-shot, fire-and-forget executor with no retry logic, no session resume, destructive cancel, and no intermediate streaming events. The E2E test `test_claude_a2a_responds` fails because `claude-agent-sdk` throws `MessageParseError` on `rate_limit_event` messages, and the executor has no recovery strategy.

The `TeamCoordinator` (`src/vaultspec/orchestration/team.py`) dispatches tasks correctly but cannot stream progress from long-running tasks, has no session-level continuity across dispatch rounds, and has a cancel propagation gap during team dissolution.

The [[2026-02-21-claude-a2a-overhaul-research]] synthesized findings from the protocol gap analysis, A2A layer audit, and reference implementations (`a2a-python-sdk`, `acp-claude-code`, `a2a-educational`). This ADR addresses the 7 executor-level and 3 coordinator-level findings.

## Considerations

### Tech Stack Divergence

The reference implementations do NOT use the same tech stack as our executor:

- **python-a2a** (980 stars): Uses `anthropic.Anthropic` directly — raw REST calls via `client.messages.create()`. Rate limits handled at the HTTP level (429 status). No subprocess. No parse errors. Session history maintained via in-memory `_conversation_histories` dict per `conversation_id`.

- **acp-claude-code** (235 stars): TypeScript SDK (`@anthropic-ai/claude-code`). Stateless `query()` function. Session resume via `resume` parameter. `AbortController` for cancel. Patterns adapted (not ported) for our Python ACP bridge in Phase 1 ([[2026-02-21-claude-acp-bidirectional-adr]]).

- **a2a-python-sdk** (official): The A2A protocol SDK. We already use this (`A2AClient`, `DefaultRequestHandler`, `InMemoryTaskStore`, `TaskUpdater`). No changes needed to our usage of this SDK.

Our executor uses **`claude-agent-sdk`** — a Python wrapper around the Claude CLI subprocess (`ClaudeSDKClient` with `connect()`, `query()`, `receive_messages()`). This introduces:
- `rate_limit_event` parse bug (upstream `MessageParseError`)
- Subprocess lifecycle management (`connect`/`disconnect`)
- `CLAUDECODE` env var stripping for nested invocations
- No native session resume (must extract `session_id` from stream)

**Conclusion:** We cannot port reference code directly. We adapt patterns to work within `claude-agent-sdk` constraints, just as Phase 1 did for the ACP bridge. The executor architecture remains subprocess-based.

### Phase 1 Precedent

The Phase 1 ACP bridge overhaul ([[2026-02-21-claude-acp-bidirectional-adr]]) established patterns that directly apply here:

- **Session ID extraction from SDK messages**: `ResultMessage` and `StreamEvent` carry `session_id`. The ACP bridge now extracts and stores it in per-session state. The A2A executor should do the same.
- **Non-destructive cancel**: The ACP bridge uses `asyncio.Event` per session, calls `interrupt()` without `disconnect()`. The same pattern applies.
- **Per-session state**: The ACP bridge moved from bridge-level singletons to `_SessionState` per session. The A2A executor needs per-context state for multi-turn.
- **`receive_response()` over `receive_messages()`**: The ACP bridge switched from raw `receive_messages()` to filtered `receive_response()` for robustness. The A2A executor should do the same.

### DI and Testing Constraints

The executor uses constructor DI (`client_factory`, `options_factory`) for test injection. Tests in `test_claude_executor.py` use `_InProcessSDKClient` (a real type implementing the SDK client interface) and `_OptionsRecorder`. No mocking is allowed. All new features must be testable through this DI mechanism.

## Constraints

- **Upstream SDK immutability**: Cannot modify `claude-agent-sdk`. The `rate_limit_event` parse bug remains. Must catch `MessageParseError` and implement retry.

- **No mocks in tests**: DI-injected recorders only. Existing `_InProcessSDKClient` and `_OptionsRecorder` patterns must be extended, not replaced.

- **Backward compatibility**: `TeamCoordinator` callers depend on `dispatch_parallel()`, `collect_results()`, and `dissolve_team()` signatures. Changes must be additive.

- **`claude-agent-sdk` architecture**: Persistent subprocess via `ClaudeSDKClient`. Cannot adopt stateless "fresh query per turn" pattern. Must work within `connect() → query() → receive_*() → disconnect()` lifecycle.

- **Second of six protocol cases**: Decisions here must be consistent with Phase 1 (ACP bridge) and generalizable to the remaining four cases (Claude A2A team, Gemini A2A subagent, Gemini A2A team).

- **Test baseline**: 69/69 non-E2E tests pass. 1 E2E failure (`test_claude_a2a_responds`). No regressions allowed in the 69 passing tests.

## Implementation

Five decisions, ordered by priority. References specific findings from [[2026-02-21-claude-a2a-overhaul-research]] and [[2026-02-21-protocol-gap-analysis-research]].

### Decision 1: Rate Limit Handling with Bounded Retry

**Research finding**: P0 — rate_limit_event crash. `MessageParseError` from `rate_limit_event` kills the stream. The `_finalised` fallback is unreliable.

**Gap analysis finding**: P0 #6 — "A2A Executor Uses `receive_messages()` Instead of `receive_response()`"

Switch from `receive_messages()` to `receive_response()` for consistency with the ACP bridge (Phase 1). Wrap the streaming loop in a bounded retry (3 attempts, exponential backoff: 1s, 2s, 4s). On `MessageParseError`, check `exc.data` for `rate_limit_event` — if detected, wait and retry the entire `query() → stream` cycle. On non-rate-limit parse errors, log and continue the stream.

**What changes in `execute()`**:

- Replace `receive_messages().__aiter__().__anext__()` pattern with `async for msg in sdk_client.receive_response()`.
- Wrap the query+stream cycle in a retry loop with configurable `max_retries` (default 3) and `base_delay` (default 1.0s).
- On `MessageParseError`: inspect `exc.data` for `"rate_limit"` substring. If rate limit, increment retry counter, await exponential backoff, reconnect if needed, and re-query. If not rate limit, log at warning and continue stream.
- After max retries exhausted, fail the task with a descriptive error via `updater.failed()`.

**What changes in `__init__()`**:

- Add `max_retries: int = 3` and `retry_base_delay: float = 1.0` parameters.

### Decision 2: Session Resume for Multi-Turn A2A

**Research finding**: P1 — No session resume. Each `execute()` creates a fresh `ClaudeSDKClient`. Multi-turn conversations within the same `context_id` are impossible.

Store `session_id` from `ResultMessage` per `context_id`. On subsequent `execute()` calls with the same `context_id`, pass the stored `session_id` as the `resume` parameter to `ClaudeAgentOptions`.

**What changes**:

- Add `_session_ids: dict[str, str]` to `__init__()` — maps `context_id` to Claude `session_id`.
- Add `_session_ids_lock: asyncio.Lock` for thread-safe access.
- In the streaming loop: when `ResultMessage` is received, extract `msg.session_id` (if present) and store in `_session_ids[context_id]`.
- In `execute()`: before building options, check `_session_ids.get(context_id)`. If present, set `resume=session_id` in the options kwargs.

**Reference pattern**: `python-a2a` maintains `_conversation_histories` per `conversation_id`. Our equivalent is Claude's server-side session identified by `session_id`. We store the ID, Claude stores the history.

### Decision 3: Non-Destructive Cancel

**Research finding**: P1 — Cancel is destructive. `cancel()` calls `interrupt()` + `disconnect()`. The SDK client is destroyed. Cannot resume after cancel.

**Gap analysis finding**: P0 #2 — analogous to ACP bridge cancel bug.

Replace destructive cancel with `interrupt()` only. The SDK client stays connected. The session's `session_id` is preserved for future `execute()` calls.

**What changes in `cancel()`**:

- Remove `await client.disconnect()` from cancel flow.
- Keep `client.interrupt()` to stop the current stream.
- Do NOT pop the client from `_active_clients` — it remains for potential re-use.
- Add a per-task cancel tracking: `_cancelled_tasks: set[str]` to track which tasks were cancelled.
- In `execute()`: check `_cancelled_tasks` at stream start and after each message. Clear the task from the set at the start of a new `execute()` for the same `task_id`.

**What changes in `execute()` finally block**:

- Only `disconnect()` if the task completed or failed (not if cancelled).
- Pop from `_active_clients` only on completion, failure, or explicit cleanup.

### Decision 4: AssistantMessage.error Checking

**Research finding**: P1 — No `AssistantMessage.error` checking. The `.error` field (which can be `"rate_limit"`, `"authentication_failed"`, etc.) is ignored.

Check `AssistantMessage.error` in the streaming loop. If set, treat as a retriable error (for `"rate_limit"`) or terminal error (for others).

**What changes in the streaming loop**:

- After receiving an `AssistantMessage`, check `msg.error`.
- If `msg.error == "rate_limit"`: trigger the retry logic from Decision 1.
- If `msg.error` is any other non-None value: emit `updater.failed()` with the error message and break the loop.
- If `msg.error is None`: process content blocks as normal.

### Decision 5: Streaming Progress Events

**Research finding**: P2 — No intermediate streaming events. Only `working` → `completed/failed`. Rich A2A clients see no progress.

Emit `TaskArtifactUpdateEvent` during streaming to provide progress visibility. Emit status updates on retry and cancel.

**What changes in the streaming loop**:

- On each `AssistantMessage` with text content: emit an intermediate artifact update via `updater.update_status()` with a message containing the latest text chunk.
- On rate limit retry: emit status update noting "Rate limited, retrying (attempt N/M)".
- On cancel detection: emit status update noting "Task cancelled" before cleanup.

**What this enables**: A2A clients polling via `tasks/get` or streaming via SSE see incremental progress instead of a single final result.

## Rationale

### Why Retry at Executor Level (not SDK Level)

The `rate_limit_event` is a `claude-agent-sdk` upstream bug — the SDK doesn't recognize this message type. We cannot fix the SDK. Retry at the executor level is the only option. Bounded retry (3 attempts, exponential backoff) prevents infinite loops while giving transient rate limits time to clear. This matches standard HTTP client retry patterns and is consistent with how `python-a2a` handles 429 responses.

### Why `receive_response()` Over `receive_messages()`

The ACP bridge (Phase 1) switched to `receive_response()` which provides filtered, higher-level messages. The A2A executor still uses raw `receive_messages()` which exposes parse errors for unknown message types. Consistency across protocol layers reduces maintenance burden and makes the code more robust. Both layers now use the same streaming API.

### Why Per-Context Session IDs (not Per-Task)

A2A `context_id` groups related tasks into a session. Multiple tasks in the same context should share conversation history. Storing `session_id` per `context_id` (not per `task_id`) means follow-up tasks in the same team session resume the conversation naturally. This aligns with the `TeamCoordinator`'s use of `context_id = team_id` ([[2026-02-20-a2a-team-adr]], Decision 2).

### Why Non-Destructive Cancel (Consistent with Phase 1)

Phase 1 established the pattern: `interrupt()` without `disconnect()`. The A2A executor should follow the same pattern for consistency. Destructive cancel forces a full reconnect (subprocess spawn, ~200-500ms on Windows) for the next task. Non-destructive cancel preserves the subprocess and session state. The saved `session_id` enables resume even if the client is eventually recreated.

### Why Streaming Progress (not Just Final Result)

The A2A spec supports `TaskStatusUpdateEvent` and `TaskArtifactUpdateEvent` for exactly this purpose. Our `TeamCoordinator` already calls `A2AClient.send_message()` which could be upgraded to `send_message_streaming()` in a future phase. Emitting intermediate events from the executor is a prerequisite for streaming dispatch at the coordinator level.

## Consequences

### Positive

- E2E test `test_claude_a2a_responds` should pass after retry logic handles `rate_limit_event`.
- Multi-turn A2A conversations via `context_id` grouping will preserve history.
- Cancel preserves session state — cancelled tasks can be retried or followed up.
- Streaming progress enables richer A2A client experiences.
- Consistent patterns with Phase 1 ACP bridge reduce cognitive load and maintenance.

### Negative

- Retry logic adds complexity to `execute()`. The method grows from ~90 lines to ~120 lines. Consider extracting the retry loop into a helper.
- Per-context `_session_ids` dict grows unbounded over the executor's lifetime. Consider an LRU eviction strategy if the executor is long-lived.
- Non-destructive cancel means the subprocess persists after cancellation. If many tasks are cancelled, subprocesses accumulate until `disconnect()` is explicitly called.
- Streaming progress increases the number of events emitted per task. For tasks with many `AssistantMessage` chunks, this could be verbose.

### Migration

- Existing unit tests (`test_claude_executor.py`) must be extended to cover retry, session resume, and non-destructive cancel. The DI pattern (`_InProcessSDKClient`) supports this without mocking.
- `TeamCoordinator` callers are unaffected — the coordinator dispatches via `A2AClient`, not directly to the executor.
- The `_InProcessSDKClient` test double needs methods to simulate `MessageParseError` for retry testing and `session_id` on `ResultMessage` for resume testing.
- This is the second of six protocol cases. The retry and session resume patterns will be applied to the Gemini A2A executor in a future phase.

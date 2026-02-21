---
tags:
  - "#plan"
  - "#claude-a2a-overhaul"
date: "2026-02-21"
related:
  - "[[2026-02-21-claude-a2a-overhaul-adr]]"
  - "[[2026-02-21-claude-a2a-overhaul-research]]"
  - "[[2026-02-21-protocol-gap-analysis-research]]"
  - "[[2026-02-21-claude-acp-bidirectional-adr]]"
---

# `claude-a2a-overhaul` implementation plan

Overhaul `ClaudeA2AExecutor` per [[2026-02-21-claude-a2a-overhaul-adr]]: add bounded retry
on rate limit, session resume via `context_id`, non-destructive cancel, `AssistantMessage.error`
checking, and streaming progress events. Extend test infrastructure to cover all new behaviors
without mocking.

## Proposed Changes

Five ADR decisions implemented across three phases. The executor at
`src/vaultspec/protocol/a2a/executors/claude_executor.py` is the primary target.
Test infrastructure at `src/vaultspec/protocol/a2a/tests/test_claude_executor.py`
and `conftest.py` is extended in parallel.

The `TeamCoordinator` (`src/vaultspec/orchestration/team.py`) is NOT modified in this
plan. Streaming dispatch and coordinator-level enhancements are deferred to a future
phase per [[2026-02-21-claude-a2a-overhaul-research]] Finding 6.

## Tasks

- `Phase 1: Core Reliability (ADR Decisions 1 + 4)`
    1. **Switch streaming API**: Replace `receive_messages().__aiter__().__anext__()`
       pattern with `async for msg in sdk_client.receive_response()` in `execute()`.
       This aligns with the ACP bridge (Phase 1) and filters out raw parse errors.
    2. **Add retry parameters**: Add `max_retries: int = 3` and
       `retry_base_delay: float = 1.0` to `__init__()`.
    3. **Implement bounded retry loop**: Wrap the `query() → stream` cycle in a retry
       loop. On `MessageParseError`, inspect `exc.data` for `"rate_limit"`. If rate
       limit detected, await `base_delay * 2^attempt` seconds then retry. After
       `max_retries` exhausted, fail the task.
    4. **Add `AssistantMessage.error` checking**: After receiving an `AssistantMessage`,
       check `msg.error`. If `"rate_limit"`, trigger retry. If other non-None error,
       fail the task immediately.
    5. **Update `_InProcessSDKClient`**: Add `receive_response()` method that yields
       the same messages as `receive_messages()`. Add ability to inject
       `MessageParseError` into the stream for retry testing.
    6. **Write tests**: Test successful retry after rate limit. Test failure after max
       retries exhausted. Test `AssistantMessage.error` handling (rate_limit triggers
       retry, other errors fail). Test non-rate-limit `MessageParseError` is logged
       and skipped.
    - **Files modified**: `claude_executor.py`, `test_claude_executor.py`

- `Phase 2: Session Resume + Non-Destructive Cancel (ADR Decisions 2 + 3)`
    1. **Add per-context session tracking**: Add `_session_ids: dict[str, str]` and
       `_session_ids_lock: asyncio.Lock` to `__init__()`.
    2. **Extract session ID from `ResultMessage`**: In the streaming loop, when
       `ResultMessage` is received, extract `msg.session_id` (if present) and store
       in `_session_ids[context_id]`.
    3. **Pass `resume` on subsequent executions**: In `execute()`, before building
       options, check `_session_ids.get(context_id)`. If present, include
       `resume=session_id` in the options kwargs dict.
    4. **Make cancel non-destructive**: In `cancel()`, remove
       `await client.disconnect()`. Keep `client.interrupt()`. Do NOT pop client from
       `_active_clients`. Add `_cancelled_tasks: set[str]` tracking.
    5. **Adjust execute() finally block**: Only call `disconnect()` on completion or
       failure, not after cancellation. Check `_cancelled_tasks` in the streaming loop
       to break early.
    6. **Update `_OptionsRecorder`**: Verify that `resume` parameter is captured when
       present.
    7. **Write tests**: Test session ID extraction from `ResultMessage`. Test `resume`
       is passed on second `execute()` with same `context_id`. Test cancel does not
       disconnect. Test cancelled task can be followed up with new execute.
    - **Files modified**: `claude_executor.py`, `test_claude_executor.py`

- `Phase 3: Streaming Progress Events (ADR Decision 5)`
    1. **Emit intermediate status updates**: On each `AssistantMessage` with text
       content, call `updater.update_status()` with the latest text chunk.
    2. **Emit retry status**: On rate limit retry, emit status update with
       "Rate limited, retrying (attempt N/M)" message.
    3. **Emit cancel status**: On cancel detection in streaming loop, emit status
       update before breaking.
    4. **Write tests**: Test intermediate status events are emitted during streaming.
       Test retry status events. Verify event ordering: working → intermediate →
       completed/failed.
    - **Files modified**: `claude_executor.py`, `test_claude_executor.py`

## Parallelization

Phases 1 and 2 share the `execute()` method and must be sequential — Phase 1
restructures the streaming loop (retry wrapper), Phase 2 adds session tracking and
cancel changes to the same loop. Phase 3 (streaming events) adds to the loop
established by Phases 1-2 and should follow them.

**Recommended**: Sequential execution. Phase 1 → Phase 2 → Phase 3. Each phase has
its own step record.

## Verification

- **Baseline preservation**: All 69 non-E2E tests must continue to pass after each phase.
- **New test coverage**: Each phase adds tests for its specific behaviors. Target: at
  least 6 new test cases (Phase 1: 4, Phase 2: 4, Phase 3: 3).
- **E2E validation**: After Phase 1, the `test_claude_a2a_responds` E2E test should
  have improved resilience to `rate_limit_event`. However, E2E tests depend on external
  services and may still be flaky. The retry logic is verified via DI-based tests.
- **Backward compatibility**: `TeamCoordinator` and CLI callers are not modified and
  should work unchanged. Verify by running `test_team.py` and `test_integration_a2a.py`
  after all phases.
- **Pattern consistency**: Compare the final `claude_executor.py` streaming loop
  structure with the ACP bridge's `prompt()` loop in `claude_bridge.py`. Both should
  follow the same patterns: `receive_response()`, session ID extraction, non-destructive
  cancel, `asyncio.Event`-based or set-based cancel tracking.

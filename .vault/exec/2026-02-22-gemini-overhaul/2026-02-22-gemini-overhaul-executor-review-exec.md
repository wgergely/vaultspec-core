---
tags:
  - "#exec"
  - "#gemini-overhaul"
date: "2026-02-22"
related:
  - "[[2026-02-22-gemini-overhaul-adr]]"
  - "[[2026-02-22-gemini-a2a-review]]"
  - "[[2026-02-21-claude-a2a-overhaul-adr]]"
---
# `gemini-overhaul` code review -- Phase 2: A2A Executor Hardening (Decision 5)

**Status:** `PASS`

## Audit Context

- **ADR:** `[[2026-02-22-gemini-overhaul-adr]]` -- Decision 5 (5a through 5e)
- **Pre-hardening review:** `[[2026-02-22-gemini-a2a-review]]` (status: REVISION REQUIRED)
- **Gold standard:** `src/vaultspec/protocol/a2a/executors/claude_executor.py`
- **Scope:** Files reviewed:
  - `src/vaultspec/protocol/a2a/executors/gemini_executor.py` (279 lines)
  - `src/vaultspec/protocol/a2a/tests/test_gemini_executor.py` (586 lines)
  - `src/vaultspec/protocol/a2a/tests/conftest.py` (shared fixtures)
  - `src/vaultspec/protocol/acp/types.py` (SubagentResult definition)
  - `src/vaultspec/protocol/a2a/executors/claude_executor.py` (gold standard cross-reference)

## ADR Compliance: Sub-Decision Assessment

### Decision 5a -- Bounded Retry with Exponential Backoff: COMPLIANT

- Constructor has `max_retries: int = 3` and `retry_base_delay: float = 1.0` (line 91-92). Both are keyword-only with defaults. Backward compatible.
- Retry loop wraps `run_subagent()` call at lines 128-244 via `while True` with attempt tracking.
- Exception classification via `_is_retryable()` (lines 48-57):
  - Non-retryable first: `FileNotFoundError`, `ValueError`, `TypeError` return `False`.
  - `FileNotFoundError` is correctly special-cased before `OSError` check (it is an `OSError` subclass).
  - Retryable types: `subprocess.TimeoutExpired`, `ConnectionError`, `OSError` via `_RETRYABLE_EXCEPTIONS` tuple (lines 38-42).
  - String patterns: `"rate_limit"`, `"timeout"`, `"connection"` via `_RETRYABLE_PATTERNS` (line 45).
  - String matching uses `.lower()` for case-insensitive comparison.
- Delay formula at line 180: `self._retry_base_delay * (2**attempt)` -- matches ADR spec and Claude executor pattern exactly.
- `TaskState.working` status emitted with retry count at lines 181-196.
- After `max_retries` exhausted, task fails via `updater.failed()` at lines 172-177 with log at lines 162-171.
- Cancel-aware backoff sleep: uses `asyncio.wait_for(cancel_event.wait(), timeout=delay)` at lines 208-216. This is an improvement over the Claude executor, which uses `asyncio.sleep(delay)` without cancel awareness during backoff.

### Decision 5b -- Heartbeat Progress Events: COMPLIANT

- Background `asyncio.Task` created via `asyncio.create_task(self._heartbeat(...))` at lines 149-151.
- `_heartbeat()` method at lines 252-261 emits periodic `TaskState.working` via `updater.update_status()`.
- Default interval is `_HEARTBEAT_INTERVAL_SECS = 5.0` (line 35), matching ADR spec of ~5 seconds.
- Interval is DI-injectable via `_heartbeat_interval` constructor parameter (line 93) for fast tests.
- Heartbeat cancelled in the `finally` block at lines 218-221: `heartbeat_task.cancel()` followed by awaiting with `suppress(asyncio.CancelledError)`.
- Uses `contextlib.suppress(RuntimeError)` at line 260 to guard against post-terminal status updates.
- Double-check of `cancel_event.is_set()` at line 258 before emitting -- prevents unnecessary update after cancel.

### Decision 5c -- Non-destructive Cancel: COMPLIANT

- `_running_tasks: dict[str, asyncio.Task]` at line 102.
- `_cancel_events: dict[str, asyncio.Event]` at line 103.
- `execute()` creates `cancel_event` at line 122, stores in `_cancel_events` under lock at lines 123-124.
- `execute()` wraps `run_subagent()` in `asyncio.create_task()` at line 138 and stores in `_running_tasks` under lock at lines 146-147.
- `execute()` handles `asyncio.CancelledError` at lines 155-158 to mark task as cancelled via `updater.cancel()`.
- `cancel()` method at lines 263-278:
  - Sets cancel event under lock (line 274-275).
  - Cancels asyncio task under lock (line 276-277).
  - Emits `updater.cancel()` at line 278.
- Pattern matches ADR pseudocode from Decision 5c exactly.
- `cancel()` has a docstring (lines 264-268) documenting its behavior.
- Cleanup in `finally` block at lines 247-250 removes both `_cancel_events` and `_running_tasks` entries.

### Decision 5d -- Concurrency Protection: COMPLIANT

- `_tasks_lock = asyncio.Lock()` at line 104 protects `_running_tasks` and `_cancel_events`.
- `_session_ids_lock = asyncio.Lock()` at line 106 protects `_session_ids`.
- All shared mutable state access goes through locks:
  - `_cancel_events` write: line 123-124 (under `_tasks_lock`).
  - `_running_tasks` write: line 146-147 (under `_tasks_lock`).
  - `_running_tasks` cleanup: line 222-223 (under `_tasks_lock`).
  - `_cancel_events` and `_running_tasks` final cleanup: lines 248-250 (under `_tasks_lock`).
  - `_session_ids` write: lines 227-228 (under `_session_ids_lock`).
  - `cancel()` reads/writes: lines 273-277 (under `_tasks_lock`).
- The Gemini executor is actually more disciplined than the Claude executor here. In the Claude executor, `_cancel_events` access is NOT protected by any lock (lines 125, 345-347 of `claude_executor.py`). The Gemini executor correctly protects all dict operations under `_tasks_lock`.

### Decision 5e -- Session Resume Infrastructure: COMPLIANT

- `_session_ids: dict[str, str]` at line 105 maps `context_id` to session identifier.
- After successful `run_subagent()`, `result.session_id` is stored in `_session_ids[context_id]` at lines 226-228 (under `_session_ids_lock`), with a guard: only stored when `result.session_id` is truthy (line 226).
- The infrastructure is built and ready for when `run_subagent()` gains `resume_session_id` parameter support.

## Findings

### Critical / High (Must Fix)

None.

### Medium / Low (Recommended)

- **[MEDIUM]** `src/vaultspec/protocol/a2a/executors/gemini_executor.py:22` -- Module-level import of `run_subagent`. This ties the executor module to `orchestration.subagent` at import time. If `orchestration.subagent` acquires heavy transitive imports, this could slow down import of the entire `protocol.a2a.executors` package. Consider lazy-importing inside a `_default_run_subagent` wrapper function. **Pre-existing issue, not introduced by this change.**

- **[LOW]** `src/vaultspec/protocol/a2a/executors/gemini_executor.py:243` -- Hardcoded "Done" fallback. When `response_text` is empty or None, the completion message uses `text or "Done"`. The Claude executor does not use a hardcoded fallback. This is a minor behavioral difference and was pre-existing from the original skeleton. **Pre-existing issue, not introduced by this change.**

- **[LOW]** `src/vaultspec/protocol/a2a/executors/gemini_executor.py:180` -- Delay formula starts at `2*base` (attempt=1) rather than `1*base` (attempt=0). This means the first retry delay is 2 seconds (with default base=1.0) rather than 1 second. This matches the Claude executor exactly and is consistent with the ADR formula `retry_base_delay * 2^attempt` when `attempt` is incremented before computation. Not a bug, just worth noting that the minimum backoff is 2x the base.

## Pre-Hardening Issue Resolution

Cross-referencing against all findings from `[[2026-02-22-gemini-a2a-review]]`:

| Finding | Severity | Status | Resolution |
|---------|----------|--------|------------|
| No retry on transient errors | HIGH | RESOLVED | Bounded retry with exponential backoff (Decision 5a). `max_retries=3`, `retry_base_delay=1.0`, exception classification via `_is_retryable()`. |
| No streaming progress events | HIGH | RESOLVED | Heartbeat background task emitting `TaskState.working` every 5 seconds (Decision 5b). |
| No session resume via context_id | HIGH | RESOLVED | Infrastructure built: `_session_ids` dict with `_session_ids_lock`, stores `result.session_id` keyed by `context_id` (Decision 5e). Full resume deferred to upstream `run_subagent()` changes. |
| Cancel is a no-op | HIGH | RESOLVED | Cancel sets event, cancels asyncio task, emits `updater.cancel()` (Decision 5c). Running subprocess is terminated via `asyncio.Task.cancel()`. |
| No concurrency protection | HIGH | RESOLVED | `_tasks_lock` protects `_running_tasks` and `_cancel_events`. `_session_ids_lock` protects `_session_ids` (Decision 5d). |
| No docstring on cancel() | MEDIUM | RESOLVED | Docstring added at lines 264-268. |
| No concurrent execution test | MEDIUM | RESOLVED | `TestGeminiA2AExecutorConcurrency::test_concurrent_execution` added. |
| No None response_text test | MEDIUM | RESOLVED | `TestGeminiA2AExecutorSessionResume::test_none_response_text` added. |

All 8 findings from the pre-hardening review are resolved.

## Feature Parity Matrix: Gemini vs. Claude A2A Executor (Post-Hardening)

| Feature | Claude | Gemini | Gap |
|---------|--------|--------|-----|
| Basic execute (prompt -> result) | Yes | Yes | -- |
| Error handling (exception -> failed task) | Yes | Yes | -- |
| Cancel (emit canceled status) | Yes | Yes | -- |
| Cancel (interrupt running task) | Yes (SDK interrupt) | Yes (asyncio.Task.cancel) | Equivalent |
| Retry on transient errors | Yes (rate-limit focus) | Yes (broader: OSError, ConnectionError, string patterns) | Gemini is broader |
| Session resume infrastructure | Yes (active: passes `resume=session_id`) | Yes (passive: stores session_id, awaits upstream) | Partial -- see note |
| Streaming progress events | Yes (throttled, per-message) | Yes (heartbeat, periodic) | Architectural diff |
| Concurrency locks | Yes (partial: `_clients_lock`, `_session_ids_lock`) | Yes (full: `_tasks_lock`, `_session_ids_lock`) | Gemini is more disciplined |
| Cancel-aware backoff | No (`asyncio.sleep`) | Yes (`asyncio.wait_for` on cancel event) | Gemini is better |
| Constructor DI for testing | Yes | Yes | -- |
| Logging (info, debug, error) | Yes | Yes | -- |
| Type annotations | Yes | Yes | -- |
| Public API doc comments | Yes | Yes | -- |

**Session resume note**: The Claude executor actively passes `resume=session_id` to the SDK because `ClaudeAgentOptions` supports it. The Gemini executor stores the session_id but cannot pass it to `run_subagent()` yet because that function does not accept a `resume_session_id` parameter. This is an expected limitation documented in ADR Decision 5e.

## Test Coverage Assessment

### Original Tests (5): All present and passing

| Test | Status |
|------|--------|
| `test_gemini_executor_completes_successfully` | PASS |
| `test_gemini_executor_handles_error` | PASS |
| `test_gemini_executor_cancel` | PASS |
| `test_gemini_executor_empty_response` | PASS |
| `test_gemini_executor_custom_params` | PASS |

### New Tests (10): All passing

| Test | Decision | What it covers |
|------|----------|----------------|
| `test_retry_on_transient_error_then_success` | 5a | ConnectionError retries then succeeds |
| `test_retry_exhaustion_fails` | 5a | max_retries exhausted -> failed |
| `test_non_retryable_error_fails_immediately` | 5a | FileNotFoundError -> no retry |
| `test_rate_limit_string_triggers_retry` | 5a | String pattern "rate_limit" -> retryable |
| `test_cancel_during_execute` | 5c | Cancel interrupts running task |
| `test_heartbeat_emits_working_events` | 5b | Heartbeat fires during slow task |
| `test_concurrent_execution` | 5d | Two concurrent executions complete |
| `test_session_id_stored_by_context` | 5e | session_id stored by context_id |
| `test_none_session_id_not_stored` | 5e | None session_id not stored |
| `test_none_response_text` | 5e (bonus) | None response_text -> "Done" fallback |

### Test Quality

- **No mocking**: All tests use constructor DI (`_RunSubagentRecorder`, `_FailThenSucceedRecorder`, inline callables). No `unittest.mock`, `pytest-mock`, or `monkeypatch`. Compliant with project ban.
- **Test doubles are plain classes**: `_RunSubagentRecorder` and `_FailThenSucceedRecorder` are simple async callables with configurable behavior.
- **Speed**: All 15 tests complete in 0.59 seconds (well under 1 second per test). The slowest test (`test_heartbeat_emits_working_events`) takes 167ms due to the intentional `delay=0.15` sleep.
- **Regression safety**: Full A2A test suite (72 tests, excluding E2E) passes with 0 failures.

### Coverage Gaps (Minor)

- No test for `OSError` or `subprocess.TimeoutExpired` retryability. The `_is_retryable()` function covers these types but only `ConnectionError` and `FileNotFoundError` are tested. Low risk since the classification logic is straightforward.
- No test for the cancel-aware backoff sleep (the `asyncio.wait_for(cancel_event.wait(), timeout=delay)` path at lines 208-216 where cancel fires during retry backoff). This is a nice improvement over the Claude executor but is not directly tested.

## Backward Compatibility

- `__init__` signature: `root_dir`, `model`, `agent_name`, `run_subagent` preserved as keyword-only. New parameters `max_retries`, `retry_base_delay`, `_heartbeat_interval` are keyword-only with defaults. No breaking change.
- `execute(context, event_queue)` signature: unchanged.
- `cancel(context, event_queue)` signature: unchanged.
- Public API `__all__ = ["GeminiA2AExecutor"]`: unchanged.

## Recommendations

No blocking issues. The implementation is clean, correct, and fully compliant with ADR Decision 5 sub-decisions 5a through 5e. All pre-hardening HIGH findings are resolved.

**Optional improvements** (not blocking):

- Consider adding a test for the cancel-during-retry-backoff path to validate the `asyncio.wait_for(cancel_event.wait(), timeout=delay)` behavior.
- Consider lazy-importing `run_subagent` to avoid import-time coupling with the orchestration layer (pre-existing, low priority).

## Notes

The Gemini executor hardening goes slightly beyond matching the Claude executor in two areas:

1. **Lock discipline**: The Gemini executor protects `_cancel_events` under `_tasks_lock`, while the Claude executor accesses `_cancel_events` without any lock. This is technically more correct for concurrent access safety.

2. **Cancel-aware backoff**: The Gemini executor uses `asyncio.wait_for(cancel_event.wait(), timeout=delay)` during retry backoff, so a cancel signal during backoff is responded to immediately rather than waiting for the full delay to expire. The Claude executor uses plain `asyncio.sleep(delay)`.

Both differences are positive deviations from the gold standard and represent legitimate improvements that could be backported to the Claude executor in future work.

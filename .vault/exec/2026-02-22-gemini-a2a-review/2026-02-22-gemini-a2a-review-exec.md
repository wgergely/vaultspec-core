---
tags:
  - "#exec"
  - "#gemini-a2a-review"
date: "2026-02-22"
related:
  - "[[2026-02-15-a2a-adr]]"
  - "[[2026-02-20-a2a-team-adr]]"
  - "[[2026-02-21-gemini-provider-auth-strategy-adr]]"
  - "[[2026-02-21-claude-a2a-overhaul-adr]]"
  - "[[2026-02-20-a2a-team-gemini-research]]"
  - "[[2026-02-21-gemini-bridge-auth-research]]"
---
# `gemini-a2a-review` code review

**Status:** `REVISION REQUIRED`

## Audit Context

- **ADRs:**
  - `[[2026-02-15-a2a-adr]]` -- foundational A2A architecture (Phase 4: GeminiA2AExecutor)
  - `[[2026-02-20-a2a-team-adr]]` -- multi-agent team coordination, Gemini as A2A server target
  - `[[2026-02-21-gemini-provider-auth-strategy-adr]]` -- Gemini OAuth wrangling + API key override
  - `[[2026-02-21-claude-a2a-overhaul-adr]]` -- Claude executor hardening (retry, session resume, cancel, streaming)
- **Scope:** Files reviewed:
  - `src/vaultspec/protocol/a2a/executors/gemini_executor.py` (114 lines)
  - `src/vaultspec/protocol/a2a/tests/test_gemini_executor.py` (206 lines)
  - `src/vaultspec/protocol/providers/gemini.py` (356 lines)
  - `src/vaultspec/protocol/a2a/tests/test_e2e_a2a.py` (E2E / gold standard tests)
  - `src/vaultspec/protocol/a2a/executors/base.py` (shared sandbox utilities)
  - `src/vaultspec/protocol/a2a/executors/__init__.py` (public re-exports)

## Findings

### Critical / High (Must Fix)

- **[HIGH] Feature parity gap: No retry on transient errors**
  `src/vaultspec/protocol/a2a/executors/gemini_executor.py`

  The `ClaudeA2AExecutor` was hardened with bounded retry (max 3 attempts, exponential
  back-off) on rate-limit and transient errors. The `GeminiA2AExecutor` has zero retry
  logic. When `run_subagent()` fails due to a transient error (network hiccup, Gemini
  rate limit, subprocess timeout), the task fails immediately and permanently.

  The Gemini CLI is known to hit rate limits under the OAuth free tier (60 RPM) and the
  API key free tier. In a team scenario where a `TeamCoordinator` dispatches to multiple
  agents in parallel, transient failures are expected and must be retried.

  The ADR `2026-02-21-claude-a2a-overhaul-adr` Decision 2e explicitly mandated bounded
  retry. While that ADR targeted the Claude executor specifically, the `2026-02-20-a2a-team-adr`
  Phase 4 ("Liveness + error handling: retry on failure") applies to all executors.

  **Recommendation:** Add a retry loop with configurable `max_retries` and
  `retry_base_delay` parameters, matching the Claude executor's pattern. Classify
  specific `run_subagent()` exceptions as retryable (e.g., `subprocess.TimeoutExpired`,
  connection errors) and fail immediately on non-retryable errors (e.g., missing
  executable).

- **[HIGH] Feature parity gap: No streaming progress events**
  `src/vaultspec/protocol/a2a/executors/gemini_executor.py`

  The Claude executor emits throttled `TaskState.working` status updates with
  accumulated text during streaming, giving A2A clients visibility into long-running
  tasks. The Gemini executor emits exactly two statuses: `working` at start, then
  `completed` or `failed` at end. For tasks that take 30-60+ seconds (typical for
  Gemini CLI subprocess execution), A2A clients see no intermediate progress.

  This is an architectural limitation: `run_subagent()` returns a `SubagentResult`
  after full completion -- there is no streaming interface. However, the executor
  could emit periodic heartbeat-style progress updates (e.g., "Gemini processing...")
  on a timer to prevent A2A client timeouts and provide observability.

  **Recommendation:** Consider adding a background timer that emits periodic
  `TaskState.working` updates while `run_subagent()` is running. Alternatively,
  document this as a known limitation that will be addressed when `run_subagent()`
  gains a streaming callback interface.

- **[HIGH] Feature parity gap: No session resume capability**
  `src/vaultspec/protocol/a2a/executors/gemini_executor.py`

  The Claude executor maintains `_session_ids: dict[str, str]` keyed by `context_id`,
  enabling multi-turn A2A conversations. When the same `context_id` is used in
  subsequent `execute()` calls, the Claude executor passes `resume=session_id` to
  restore conversation state.

  The Gemini executor has no equivalent. Each `execute()` call spawns a fresh
  subprocess with no memory of prior interactions. The `2026-02-20-a2a-team-adr`
  Decision 2 explicitly states that `contextId` groups related tasks into a shared
  session. Without session resume, the Gemini executor cannot participate in
  multi-turn team workflows.

  The Gemini CLI supports `--resume` for session restoration (documented in the
  research at `2026-02-20-a2a-team-gemini-research`), but `run_subagent()` does not
  currently expose this parameter.

  **Recommendation:** This requires upstream changes to `run_subagent()` to accept
  a `resume_session_id` parameter. Document this as a known gap. Track it as a
  separate work item since it requires changes outside the executor.

- **[HIGH] Feature parity gap: Cancel is a no-op with no subprocess termination**
  `src/vaultspec/protocol/a2a/executors/gemini_executor.py:108-113`

  The `cancel()` method emits a `canceled` status but does NOT terminate the running
  `run_subagent()` subprocess. Once `execute()` calls `await self._run_subagent(...)`,
  there is no mechanism to interrupt the in-flight subprocess. The cancellation event
  is consumed by the A2A framework but the Gemini CLI process continues to run,
  consuming resources.

  Contrast with the Claude executor, which maintains `_active_clients` and
  `_cancel_events` dictionaries. On cancel, it sets the cancel event (breaking the
  stream loop) and calls `client.interrupt()` to signal the SDK subprocess.

  **Recommendation:** Introduce a mechanism to cancel the in-flight `run_subagent()`
  call. Options include:
  - Wrapping the `run_subagent()` call in `asyncio.create_task()` and storing the
    task for cancellation.
  - Adding a cancel callback to `run_subagent()` that terminates the subprocess.
  - Using `asyncio.wait_for()` with an `asyncio.Event` that `cancel()` sets.

- **[HIGH] No concurrency protection**
  `src/vaultspec/protocol/a2a/executors/gemini_executor.py`

  The Claude executor uses `asyncio.Lock` instances (`_clients_lock`,
  `_session_ids_lock`) to protect shared mutable state when multiple tasks execute
  concurrently on the same executor instance. The Gemini executor has no shared
  mutable state tracking and no locks.

  While the Gemini executor currently has no `_active_clients` or `_session_ids`
  dictionaries, if retry or cancel tracking is added (per the HIGH findings above),
  concurrent task execution will require synchronization. This is a structural gap
  that should be addressed proactively.

  **Recommendation:** When implementing retry and cancel support, follow the Claude
  executor pattern of lock-protected dictionaries for active task tracking.

### Medium / Low (Recommended)

- **[MEDIUM] `_default_run_subagent` import at module level**
  `src/vaultspec/protocol/a2a/executors/gemini_executor.py:19`

  ```python
  from vaultspec.orchestration.subagent import run_subagent as _default_run_subagent
  ```

  This import ties the executor module to the orchestration layer at import time.
  If `orchestration.subagent` has heavy transitive imports, this slows down import
  of the entire `protocol.a2a.executors` package even when only `ClaudeA2AExecutor`
  is needed. The Claude executor avoids this by importing `claude_agent_sdk` at
  module level (unavoidable for type checks) but keeps its `_default_client_factory`
  as a thin wrapper.

  **Recommendation:** Consider lazy-importing `run_subagent` inside
  `_default_run_subagent` or using a string-based default. Low priority given
  current project size.

- **[MEDIUM] No doc comments on public `cancel()` method**
  `src/vaultspec/protocol/a2a/executors/gemini_executor.py:108`

  The `execute()` method is well-documented via the class docstring, but `cancel()`
  has no docstring explaining its current limitations (no subprocess termination).

  **Recommendation:** Add a docstring noting that cancel emits the A2A status but
  does not terminate the underlying subprocess.

- **[MEDIUM] Test coverage gap: no test for concurrent execution**
  `src/vaultspec/protocol/a2a/tests/test_gemini_executor.py`

  All tests run a single task at a time. There is no test verifying that two
  concurrent `execute()` calls on the same executor instance are handled correctly.
  The Claude executor tests also lack this, but the Claude executor has explicit
  locking which at least demonstrates intent.

  **Recommendation:** Add a test that dispatches two tasks concurrently via
  `asyncio.gather()` and verifies both complete independently.

- **[MEDIUM] Test coverage gap: no test for `None` response_text**
  `src/vaultspec/protocol/a2a/tests/test_gemini_executor.py`

  The tests cover `response_text=""` (empty string) and `response_text="..."` (non-empty),
  but not `response_text=None`. The executor code at line 87 does
  `result.response_text or ""`, which handles `None` correctly, but this path is
  untested.

  **Recommendation:** Add a test case with `SubagentResult(response_text=None, ...)`.

- **[LOW] Hardcoded fallback "Done" message**
  `src/vaultspec/protocol/a2a/executors/gemini_executor.py:97`

  ```python
  parts=[Part(root=TextPart(text=text or "Done"))]
  ```

  The fallback "Done" text when the response is empty is a user-facing string embedded
  in implementation. The Claude executor uses the actual response text without a
  hardcoded fallback (it sets `text` to `msg.result or ""`). Consider whether "Done"
  is the right signal or whether an empty completion is more appropriate.

  **Recommendation:** No action required -- this matches the ADR skeleton code. Note
  for future consideration.

- **[LOW] GeminiProvider: `_cached_version` is a module-level global mutable**
  `src/vaultspec/protocol/providers/gemini.py:48`

  ```python
  _cached_version: tuple[int, ...] | None = None
  ```

  This global mutable is set inside `check_version()` and persists across all
  provider instances in the process. If the Gemini CLI is upgraded mid-process
  (unlikely but possible in long-running servers), the cached version would be stale.

  **Recommendation:** No action required for current usage. Document the caching
  behavior if the provider is used in long-running A2A server processes.

- **[LOW] GeminiProvider auth: `_refresh_gemini_oauth_token` uses `urllib.request`**
  `src/vaultspec/protocol/providers/gemini.py:97-98`

  The ADR explicitly chose `urllib.request` over `httpx` to avoid adding a dependency
  for a single POST. The implementation correctly follows this decision. The
  `urlopen` call has a 10-second timeout. This is appropriate.

  No issue -- noting for completeness that the implementation matches the ADR.

## Feature Parity Matrix: Gemini vs. Claude A2A Executor

| Feature | Claude | Gemini | Gap Severity |
|---|---|---|---|
| Basic execute (prompt -> result) | Yes | Yes | -- |
| Error handling (exception -> failed task) | Yes | Yes | -- |
| Cancel (emit canceled status) | Yes | Yes | -- |
| Cancel (interrupt running subprocess) | Yes | No | HIGH |
| Cancel (non-destructive, preserve session) | Yes | N/A | HIGH (no sessions) |
| Retry on transient errors | Yes (3 attempts, exp backoff) | No | HIGH |
| Session resume via context_id | Yes | No | HIGH |
| Streaming progress events | Yes (throttled) | No | HIGH |
| Rate-limit-specific handling | Yes (MessageParseError + error field) | No | HIGH |
| Concurrency locks | Yes (asyncio.Lock) | No | MEDIUM |
| Constructor DI for testing | Yes (client_factory, options_factory) | Yes (run_subagent) | -- |
| Logging (info, debug, error) | Yes | Yes | -- |
| Type annotations | Yes | Yes | -- |
| Public API doc comments | Yes | Partial | MEDIUM |

## ADR Compliance Assessment

### `2026-02-15-a2a-adr` (foundational)

The foundational ADR (Phase 4) specifies a minimal `GeminiA2AExecutor` that delegates
to `run_subagent()`. The current implementation matches this skeleton almost exactly.
The ADR did not specify retry, session resume, or streaming -- those requirements
came from the later `2026-02-21-claude-a2a-overhaul-adr`. **Compliant with original
scope.**

### `2026-02-20-a2a-team-adr` (team coordination)

Decision 3 specifies Gemini as an A2A server target where "each inbound task spawns
a fresh Gemini CLI subprocess via ACP." The current implementation matches this.
However, Phase 4 of this ADR specifies "Liveness + error handling: retry on failure,
coordinated shutdown." The Gemini executor has no retry and no coordinated shutdown
support. **Partially compliant -- retry gap.**

### `2026-02-21-gemini-provider-auth-strategy-adr` (auth)

The auth ADR specifies a three-state check in `GeminiProvider.prepare_process()`:
API key path, OAuth refresh path, and missing-auth warning. The implementation at
`gemini.py:277-301` implements all three states exactly as specified, including:
- Debug log when `GEMINI_API_KEY` is present
- OAuth token expiry check with proactive refresh via `_refresh_gemini_oauth_token()`
- Atomic write-back via `os.replace()`
- Clear warning when no auth path is found

**Fully compliant.**

### `2026-02-21-claude-a2a-overhaul-adr` (hardening)

This ADR targeted the Claude executor specifically. Its decisions (2a-2e) were
implemented in `claude_executor.py`. The question is whether these hardening
patterns should be propagated to the Gemini executor for feature parity. The
`2026-02-20-a2a-team-adr` Phase 4 ("retry on failure") suggests they should. The
Gemini executor has none of these features. **Not directly applicable but the
team ADR creates an implicit requirement.**

## Uncommitted Changes

There are **no uncommitted changes** to `gemini_executor.py`, `test_gemini_executor.py`,
or `gemini.py`. All three files match their last committed state at `9b66618`
(src-layout restructure).

## Recommendations

The Gemini executor is a correct, minimal implementation that matches the original
Phase 4 ADR skeleton. The provider module's auth implementation fully satisfies its
ADR. However, after the Claude executor hardening pass, a significant feature parity
gap has opened. The Gemini executor is now substantially less resilient than its
Claude counterpart.

**Required before merge (for team readiness):**

1. Add retry logic with configurable `max_retries` and `retry_base_delay`, matching
   the Claude executor's pattern. Classify retryable vs. non-retryable exceptions.
2. Add cancel infrastructure: track the running task for interruption, add
   `_cancel_events` dict, use `asyncio.wait_for()` or `asyncio.create_task()` to
   enable mid-execution cancellation.
3. Add concurrency locks if any shared mutable state is introduced.
4. Add a docstring to `cancel()` documenting its behavior.

**Tracked separately (requires upstream changes):**

5. Session resume: requires `run_subagent()` to accept `resume_session_id`. File a
   follow-up work item.
6. Streaming progress: requires either a callback interface in `run_subagent()` or
   a background heartbeat timer. File a follow-up work item.

**Nice-to-have:**

7. Add test for `response_text=None` case.
8. Add concurrent execution test.

## Notes

The Gemini executor's simplicity is inherent to its architecture: it wraps a
subprocess call (`run_subagent()`) rather than a streaming SDK client. Many of the
Claude executor's hardening features (streaming progress, session resume,
non-destructive cancel) are natural consequences of the Claude SDK's streaming
interface. Achieving full parity for Gemini requires changes to the `run_subagent()`
interface itself, which is a larger scope change outside the executor module.

The provider module (`gemini.py`) is well-implemented. The OAuth refresh logic is
thorough, handles edge cases (missing fields, network errors, write failures), and
follows the ADR decisions precisely. The atomic write-back via `os.replace()` and
the 5-minute expiry buffer are good defensive patterns.

Test quality for the existing executor scope is solid: 5 tests covering success,
error, cancel, empty response, and custom parameters. The DI pattern
(`_RunSubagentRecorder`) avoids mocking entirely and follows project conventions.

# Scout-Alpha Violation Report
## Test Quality Audit — 2026-02-20

**Agent:** scout-alpha
**Scope:** 5 directories, 28 Python test files
**Date:** 2026-02-20

---

## Summary

| Violation Type | Count |
|---|---|
| `unittest.mock` / `MagicMock` / `AsyncMock` / `patch` | **0** |
| `_fake_*` / `_mock_*` / `_stub_*` / `_dummy_*` prefixes | **0** |
| Hard `pytest.skip()` inside test body | **3** |
| `pytest.mark.skipif` guards | **4** |
| Tests never invoking real production code | **3** |
| Private state mutation | **7 instances across 4 files** |
| Test doubles replacing thing under test (DI) | **2** |
| Scaffolding doubles (`StoryRelayExecutor`) | **1** |

**Files with violations: 8 of 28**

---

## `.vaultspec/lib/src/protocol/acp/tests/test_client_terminal.py`

### `TestCreateTerminalReadOnly::test_create_terminal_allowed_readwrite` [LINE 36]
**Violation**: Hard `pytest.skip()` inside test body
**Why**: The test exists and is collected by pytest but unconditionally skips — it never runs, never fails, and provides zero coverage; it is dead code that creates a false sense of test completeness.

---

## `.vaultspec/lib/src/protocol/acp/tests/test_bridge_resilience.py`

### `TestCancelTracking::test_prompt_resets_cancelled_flag` [LINE 123]
**Violation**: Private state mutation (`bridge._cancelled = True`)
**Why**: Directly setting a private attribute to engineer preconditions couples the test to implementation internals; if `_cancelled` is renamed, encapsulated, or replaced with an event, the test silently breaks rather than surfacing the change through the public API.

### `TestCancelTracking::test_cancelled_during_streaming_returns_cancelled` [LINE 151]
**Violation**: Private state mutation via `_query_hook` callback (`bridge._cancelled = True` set from inside injected hook)
**Why**: The hook injects a side effect that sets a private field on the bridge from inside a recorder callback, bypassing any state-transition logic the production code may enforce; this is indirect private mutation.

### `TestCancelTracking::test_cancelled_skips_emit_for_remaining_messages` [LINE 182]
**Violation**: Private state mutation via `_query_hook` callback (`bridge._cancelled = True`)
**Why**: Same as above — the hook directly sets `bridge._cancelled` from inside a test-controlled callback, engineering state that should be reachable only via `bridge.cancel()`.

---

## `.vaultspec/lib/src/protocol/acp/tests/conftest.py`

### `SDKClientRecorder` class [LINES 40–86]
**Violation**: Test double replacing real `claude_agent_sdk` client (used across all ACP bridge unit tests)
**Why**: `SDKClientRecorder` stands in for the real SDK client; the bridge's interaction with the actual SDK (connection lifecycle, streaming, interrupt) is never exercised by the unit tests — only the recorder's behavior is asserted.

### `ConnRecorder` class [LINES 89–96]
**Violation**: Test double replacing real ACP connection
**Why**: `ConnRecorder` replaces the real ACP `AgentSideConnection`, so no test in the bridge unit suite verifies that `session_update` payloads are valid ACP wire types or that the real connection handles them correctly.

---

## `.vaultspec/lib/src/protocol/a2a/tests/test_claude_executor.py`

### `_InProcessSDKClient` class [LINES 63–~120]
**Violation**: Test double replacing real production dependency (injected via `client_factory`)
**Why**: `ClaudeA2AExecutor`'s real job is to talk to `claude_agent_sdk`; injecting `_InProcessSDKClient` means the executor's real client interaction path (actual SDK connect, query, disconnect) is never called in these tests — the DI boundary is appropriate but the real SDK path has zero unit coverage.

### `_OptionsRecorder` class [present in file]
**Violation**: Test double replacing real options object
**Why**: `_OptionsRecorder` captures construction kwargs but never validates that the options object it produces satisfies the real SDK's requirements; it is only verified structurally, not behaviorally.

---

## `.vaultspec/lib/src/protocol/a2a/tests/test_gemini_executor.py`

### `_RunSubagentRecorder` class [LINES 29–41]
**Violation**: Test double replacing real production code path (injected via `run_subagent=recorder`)
**Why**: `GeminiA2AExecutor` delegates to `run_subagent()` as its core action; the recorder replaces this with a callable that returns a preset result, so the executor's real dispatch path (spawning the Gemini process, ACP handshake) is never exercised by these tests.

---

## `.vaultspec/lib/src/protocol/a2a/tests/test_french_novel_relay.py`

### `StoryRelayExecutor` class [LINES 185–213]
**Violation**: Scaffolding test double — tests orchestration only, not real protocol behavior
**Why**: `StoryRelayExecutor` appends a canned string to input, so `TestFrenchNovelRelayMock` validates that the relay wiring passes text between 3 executors — but it does not test any real executor logic, real A2A HTTP semantics, or real LLM output; the mock class is well-documented but confirms the harness works, not that the feature works.

### `TestFrenchNovelRelayLive` class [LINES 327–333]
**Violation**: `pytest.mark.skipif` — class skips when `claude` or `gemini` CLI is absent (`@requires_anthropic` line 331, `@requires_gemini` line 332)
**Why**: The gold-standard 3-turn live relay test silently skips in any environment without both CLIs on PATH; this test validates real French prose generation and narrative coherence across agents, so its absence in CI leaves the core feature unverified.

### `requires_anthropic` / `requires_gemini` markers [LINES 42–50]
**Violation**: `pytest.mark.skipif` defined at module level with no integration marker separation
**Why**: Module-level `skipif` marks can silently suppress tests without any visible warning in test output, making it non-obvious which environment gates are active in CI.

---

## `.vaultspec/lib/src/protocol/a2a/tests/test_e2e_a2a.py`

### `TestClaudeE2E` / `TestGeminiE2E` / `TestGoldStandardBidirectional` classes [LINES 32–40]
**Violation**: `pytest.mark.skipif` — classes skip when `claude` or `gemini` CLI is absent
**Why**: `@requires_anthropic` and `@requires_gemini` at lines 32–40 mean entire E2E test classes are silently skipped in environments without the CLIs; these are the highest-value integration tests in the A2A stack and their absence in CI leaves real executor behavior unverified.

---

## `.vaultspec/lib/src/protocol/tests/test_providers.py`

### `TestGeminiProvider::_seed_version_cache` fixture [LINES 47–54]
**Violation**: Private module-level state mutation (`gmod._cached_version = (0, 27, 0)`)
**Why**: The fixture bypasses the real subprocess call to `gemini --version` by directly injecting into a private module cache; `TestGeminiProvider` tests always run against a pinned version tuple without ever verifying that the real version-detection mechanism works.

### `TestGeminiSandboxFlag::_seed_version_cache` fixture [LINES 254–259]
**Violation**: Private module-level state mutation (`gmod._cached_version = (0, 27, 0)`)
**Why**: Identical pattern — the Gemini sandbox flag tests never invoke the real version check, so they would pass even if version detection is broken.

### `TestGeminiFeaturePassthrough::_seed_version_cache` fixture [LINES 468–473]
**Violation**: Private module-level state mutation (`gmod._cached_version = (0, 27, 0)`)
**Why**: Third occurrence — all `TestGeminiFeaturePassthrough` tests silently skip real version detection via private cache injection.

### `TestGeminiVersionCheck::test_parse_version_output` [LINES 156–166]
**Violation**: Test double — `subprocess.CompletedProcess` stub + lambda `run_fn`
**Why**: The test constructs a fake `subprocess.CompletedProcess` return and passes a lambda that returns it; `GeminiProvider.check_version` is tested only with a canned string, so format changes or subprocess errors would not be caught.

### `TestGeminiVersionCheck::test_version_cached` [LINES 168–184]
**Violation**: Test double — counting lambda replacing real subprocess
**Why**: The test verifies caching by counting how many times a fake lambda is called; the caching logic is confirmed but the real subprocess invocation path is never tested.

### `TestGeminiVersionCheck::test_executable_not_found` [LINES 186–191]
**Violation**: Test double — `raise_fnf` lambda replacing real subprocess
**Why**: The `FileNotFoundError` path is tested via an injected lambda rather than actually calling a missing executable; valid as a unit test scope, but noted as a hand-rolled stub rather than using a proper DI interface.

---

## `.vaultspec/lib/src/orchestration/tests/test_team.py`

### `_build_coordinator_with_apps` helper [LINE 90]
**Violation**: Private field mutation (`coordinator._http_client = httpx.AsyncClient(mounts=mounts)`)
**Why**: Injecting an `httpx.AsyncClient` via a private field bypasses any initialization logic in `TeamCoordinator` that configures the client (auth headers, timeouts, connection pooling); if the coordinator changes how it creates its HTTP client, the tests will silently miss those changes.

---

## `.vaultspec/lib/src/subagent_server/tests/test_mcp_tools.py`

### `TestCancelTask::test_cancel_invokes_graceful_cancel` [LINE 426]
**Violation**: Hard `pytest.skip()` inside test body
**Why**: The test is collected but unconditionally skips — it never runs, never fails, and provides zero coverage of the cancel-with-active-client path, which is the most important cancel behavior.

### `TestCancelTask::test_cancel_stops_background_task` [LINE 435]
**Violation**: Hard `pytest.skip()` inside test body
**Why**: The background asyncio.Task cancellation path is never exercised; background task management is the server's primary async safety mechanism and it has zero test coverage.

### `_init_server` autouse fixture [LINES 41–53]
**Violation**: Private global state mutation (`srv._agent_cache.clear()`, `srv._background_tasks.clear()`, `srv._active_clients.clear()`)
**Why**: The fixture resets server state by directly clearing private module-level dicts rather than through a public lifecycle API, coupling every test in this file to the implementation detail that these three collections exist as module globals with these exact names.

### Multiple dispatch and cancel tests mutating `srv.task_engine` / `srv.lock_manager` [LINES 408, 415, 444, 445, 459]
**Violation**: Private module global mutation (`srv.task_engine = fresh_task_engine`, `srv.lock_manager = lm`)
**Why**: Tests swap out module-level production objects mid-test; this is feasible only because the server module was not designed for testability — a class-based server with injectable dependencies would expose these as constructor parameters rather than mutable module globals.

### All `dispatch_agent` tests [implicit — `_init_server` installs `_noop` via `initialize_server`]
**Violation**: Core dispatch function is a no-op — tests never invoke real production code
**Why**: `initialize_server` in the autouse fixture wires up `_run_subagent_fn` with `lambda: False` / no real dispatch; `dispatch_agent` tests verify task-engine state transitions and JSON response shapes but never verify that an actual agent subprocess is started — the most critical code path is never called.

---

## Clean Files (No Violations)

The following files were read in full and contain no violations:

- `.vaultspec/lib/src/orchestration/tests/conftest.py`
- `.vaultspec/lib/src/orchestration/tests/test_utils.py`
- `.vaultspec/lib/src/orchestration/tests/test_session_logger.py`
- `.vaultspec/lib/src/orchestration/tests/test_load_agent.py`
- `.vaultspec/lib/src/orchestration/tests/test_task_engine.py`
- `.vaultspec/lib/src/protocol/acp/tests/test_bridge_lifecycle.py`
- `.vaultspec/lib/src/protocol/acp/tests/test_bridge_sandbox.py`
- `.vaultspec/lib/src/protocol/acp/tests/test_bridge_streaming.py`
- `.vaultspec/lib/src/protocol/a2a/tests/conftest.py`
- `.vaultspec/lib/src/protocol/a2a/tests/test_agent_card.py`
- `.vaultspec/lib/src/protocol/a2a/tests/test_discovery.py`
- `.vaultspec/lib/src/protocol/a2a/tests/test_unit_a2a.py`
- `.vaultspec/lib/src/protocol/a2a/tests/test_integration_a2a.py`
- `.vaultspec/lib/src/protocol/tests/conftest.py`
- `.vaultspec/lib/src/protocol/tests/test_client.py`
- `.vaultspec/lib/src/protocol/tests/test_fileio.py`
- `.vaultspec/lib/src/protocol/tests/test_sandbox.py`
- `.vaultspec/lib/src/subagent_server/tests/conftest.py`
- `.vaultspec/lib/src/subagent_server/tests/test_helpers.py`

**Note — `EchoExecutor` / `PrefixExecutor`:** Used in `test_unit_a2a.py` and `test_integration_a2a.py` where the executors ARE the thing under test (verifying executor protocol correctness and A2A server routing). Not violations. Also used in `test_team.py` as simple dependencies for testing `TeamCoordinator` — appropriate.

**Note — `test_bridge_lifecycle.py`:** Uses `SDKClientRecorder` / `make_di_bridge()` DI pattern. The bridge's lifecycle logic IS exercised; only the SDK client call is replaced. Flagged `conftest.py` as the source of the recorder doubles rather than the lifecycle tests themselves.

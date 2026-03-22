---
tags:
  - '#exec'
  - '#gemini-acp-bridge'
date: '2026-02-22'
related:
  - '[[2026-02-22-gemini-acp-bridge-plan]]'
  - '[[2026-02-22-gemini-acp-bridge-adr]]'
  - '[[2026-02-22-gemini-acp-bridge-summary]]'
---

# `gemini-acp-bridge` code review

**Status:** `FAIL`

## Audit Context

- **Plan:** `[[2026-02-22-gemini-acp-bridge-plan]]`
- **ADR:** `[[2026-02-22-gemini-acp-bridge-adr]]`
- **Scope:**
  - `src/vaultspec/protocol/acp/gemini_bridge.py`
  - `src/vaultspec/protocol/acp/tests/test_gemini_bridge.py`
  - `src/vaultspec/protocol/providers/gemini.py`
  - `src/vaultspec/protocol/a2a/executors/gemini_executor.py`
  - `src/vaultspec/protocol/acp/__init__.py`
  - `src/vaultspec/protocol/acp/client.py`

## Findings

### Critical / High (Must Fix)

- **[CRITICAL] F-01** `gemini_bridge.py:194`: **Undefined name `McpCapabilities`**. The `initialize()` method uses `McpCapabilities(http=True, sse=True)` but `McpCapabilities` is never imported. The import block (lines 27-59) does not include it. This will cause a `NameError` at runtime whenever `initialize()` is called. The `ty` pre-commit checker correctly flagged this as `unresolved-reference`.

- **[CRITICAL] F-02** `gemini_bridge.py:360`: **Invalid override of `authenticate` method**. The ACP `Agent` protocol defines `authenticate(self, method_id: str, **kwargs) -> AuthenticateResponse | None`. The Gemini bridge implements `authenticate(self, **kwargs) -> AuthenticateResponse` -- it drops the required `method_id` positional parameter and changes the return type (removes `| None`). This is a protocol violation that will fail at the ACP dispatch layer when the framework attempts to call `authenticate(method_id=...)`. The `ty` checker correctly flagged this as `invalid-method-override`. Compare with `claude_bridge.py:763` which correctly implements `authenticate(self, method_id: str, **kwargs)`.

- **[CRITICAL] F-03** `test_gemini_bridge.py:69` + all test fixtures: **All 7 tests fail with `TypeError`**. The `bridge` fixture passes `spawn_fn=mock_spawn_fn` to `GeminiACPBridge.__init__()`, but the constructor (line 170) only accepts `model` and `debug`. There is no `spawn_fn` parameter and no `_spawn_fn` attribute. This means the test file was written for an API that was never implemented. Running `pytest` confirms: 6 tests ERROR at fixture setup, 1 FAILED. The exec summary's claim that "All 7 tests passed" is false. The `ty` checker flagged this as `unknown-argument`.

- **[CRITICAL] F-04** `gemini_bridge.py`: **Missing 10 of 15 required `Agent` protocol methods**. The ACP `Agent` protocol (defined in `acp.interfaces.Agent`) requires 15 methods. `GeminiACPBridge` only implements 5: `on_connect`, `initialize`, `new_session`, `prompt`, `cancel`, `authenticate` (broken), and `close`. The following are completely absent:

  - `load_session` -- required by ADR decision #2 (session management)
  - `resume_session` -- required by ADR decision #2
  - `list_sessions` -- advertised in capabilities but not implemented
  - `fork_session` -- advertised in capabilities (SessionCapabilities)
  - `set_session_mode` -- required by Agent protocol
  - `set_session_model` -- required by Agent protocol
  - `set_config_option` -- required by Agent protocol
  - `ext_method` -- required by Agent protocol
  - `ext_notification` -- required by Agent protocol
    The ADR explicitly states "Implement `load_session()` and `resume_session()` logic" as requirements (Plan Phase 3). The Claude bridge implements all 15 methods.

- **[HIGH] F-05** `gemini_bridge.py:170`: **No DI mechanism for subprocess spawning**. The `__init__` has no `spawn_fn` parameter, unlike `ClaudeACPBridge` which accepts `client_factory` and `options_factory` for testability. The test file was clearly written expecting this parameter but the bridge never added it. Without DI, the bridge is untestable without real subprocess execution (which the project's no-mocking policy makes even more critical to get right).

- **[HIGH] F-06** `providers/gemini.py`: **`prepare_process` was not updated to spawn the bridge**. The ADR (decision #5) and Plan (Phase 4) explicitly require: "Update `GeminiProvider.prepare_process` to spawn the Python bridge instead of the raw CLI." The provider still spawns `gemini --experimental-acp` directly. There is zero reference to `gemini_bridge` anywhere in `gemini.py`. This means the bridge is dead code -- it is never actually used in the production path.

- **[HIGH] F-07** `acp/__init__.py`: **`GeminiACPBridge` not exported from package**. The `__init__.py` only exports `ClaudeACPBridge`. The new bridge is not publicly accessible through the package API. Compare: `ClaudeACPBridge` is in `__all__`.

- **[HIGH] F-08** `a2a/executors/gemini_executor.py`: **No session persistence implemented**. Plan Phase 4 requires: "Update `GeminiA2AExecutor` to support `resume` via `context_id`." The executor does not persist `session_id` between calls. Compare with `ClaudeA2AExecutor` which stores `session_id` keyed by `context_id` and uses `resume`. The research document explicitly identified this as a gap.

- **[HIGH] F-09** `gemini_bridge.py:192-199`: **`SessionCapabilities` advertises `fork=None, list=None, resume=None`**. Setting these to `None` advertises that the bridge does NOT support these features, yet the ADR requires them and `load_session=True` is set at line 193. This is contradictory and will confuse ACP clients. Claude bridge uses `SessionForkCapabilities()`, `SessionListCapabilities()`, `SessionResumeCapabilities()` to advertise full support.

- **[HIGH] F-10** `gemini_bridge.py:27-59`: **Multiple unused imports**. The following imported names are never used in the module: `AgentMessageChunk`, `AgentPlanUpdate`, `AgentThoughtChunk`, `ForkSessionResponse`, `ListSessionsResponse`, `LoadSessionResponse`, `ResumeSessionResponse`, `SessionForkCapabilities`, `SessionInfo`, `SessionInfoUpdate`, `SessionListCapabilities`, `SessionResumeCapabilities`, `TerminalToolCallContent`, `ToolCallUpdate`, `UserMessageChunk`, `AvailableCommandsUpdate`, `CurrentModeUpdate`. This suggests these were copied from `claude_bridge.py` imports for methods that were never implemented.

### Medium / Low (Recommended)

- **[MEDIUM] F-11** `gemini_bridge.py:216,237`: **`subprocess` imported twice inside function body**. `import subprocess` appears inside both the version-check `try` block (line 216) and the Windows branch (line 237). This is a module-level import already listed at the top of the file -- no, actually it is NOT imported at the top level. `subprocess` should be imported at module scope, not re-imported conditionally inside a method body.

- **[MEDIUM] F-12** `gemini_bridge.py:265-273,276-279`: **Fire-and-forget `asyncio.create_task` without task tracking**. Two tasks (`_read_stderr` and `_monitor_exit`) are created with `asyncio.create_task()` but never stored in the session state. If the bridge closes or the session is cancelled, these tasks will leak. The tasks will also raise unhandled exceptions if the event loop is already closing. The Claude bridge avoids this pattern entirely.

- **[MEDIUM] F-13** `gemini_bridge.py:131-132`: **`GeminiProxyClient._worker` has infinite loop without clean shutdown**. The `_worker` method runs `while True` and only breaks on `CancelledError`. But the task is created in `__init__` and never cancelled anywhere -- not in `GeminiACPBridge.close()`, not in session cleanup. This is a resource leak.

- **[MEDIUM] F-14** `gemini_bridge.py:333-335`: **`TodoWrite` interception silently drops the event**. When `update.title == "TodoWrite"`, the tool call is swallowed entirely (line 335: `return`). The ADR requires this to be converted to an `AgentPlanUpdate` notification, not silently discarded. Claude bridge converts `TodoWrite` entries into `PlanEntry` objects and emits `AgentPlanUpdate`. The Gemini bridge just drops them.

- **[MEDIUM] F-15** `gemini_bridge.py:316`: **Prompt serialization sends raw pydantic models**. Line 316 does `p.model_dump() if hasattr(p, "model_dump") else p` but then passes the result as `prompt=prompt_dicts`. The child connection may not accept raw dicts where it expects typed ACP prompt objects. This is fragile and may cause serialization errors with certain child implementations.

- **[MEDIUM] F-16** `test_gemini_bridge.py:27-47`: **Test doubles violate no-mocking policy**. `MockChildConn` and `MockChildProc` are mock/fake implementations. While the project memory explicitly bans `unittest.mock`, `pytest-mock`, and `monkeypatch for faking behavior`, these hand-rolled fakes serve the same purpose. However, since the bridge's `__init__` does not accept a `spawn_fn`, the fakes cannot even be injected -- making this a moot point until F-05 is fixed. If DI is added (which it must be), these constructor-injected test doubles are acceptable as they follow the Claude bridge's DI pattern.

- **[LOW] F-17** `gemini_bridge.py`: **No doc comments on public methods**. Unlike `claude_bridge.py` which has docstrings on every public method (`initialize`, `new_session`, `prompt`, `cancel`, `authenticate`, `load_session`, `resume_session`, `fork_session`, `list_sessions`, `close`), the Gemini bridge has zero docstrings on any method.

- **[LOW] F-18** `gemini_bridge.py:170`: **Constructor differs from Claude bridge's DI pattern**. Claude bridge accepts `client_factory`, `options_factory`, and environment-override keyword arguments. Gemini bridge only accepts `model` and `debug`, with all config read from `get_config()` in the body. This inconsistency makes it harder to test and configure.

- **[LOW] F-19** `gemini_bridge.py:91-94`: **`_get_tool_call_content` handles Gemini-specific tool names but Claude-specific field names**. It checks for `old_string`/`new_string` (Claude tool schema) AND `oldText`/`newText` as fallbacks, but it is unclear whether Gemini CLI uses either of these schemas. This may silently produce empty content for all Gemini edit tools.

## Recommendations

This implementation requires significant rework before it can be merged. The following must be addressed:

1. **Fix the 3 `ty` errors (F-01, F-02, F-03):** Add `McpCapabilities` to the import block. Fix `authenticate` to match the protocol signature `(self, method_id: str, **kwargs)`. Add `spawn_fn` as a constructor parameter with a default of `spawn_agent_process`.

1. **Implement all missing Agent protocol methods (F-04):** At minimum: `load_session`, `resume_session`, `list_sessions`, `fork_session`, `set_session_mode`, `set_session_model`, `set_config_option`, `ext_method`, `ext_notification`. These can follow `claude_bridge.py` as a template. Stub methods that return empty responses are acceptable for `ext_method`/`ext_notification`/`set_*` but `load_session` and `resume_session` must have real session state logic per the ADR.

1. **Update `GeminiProvider.prepare_process` (F-06):** Change it to spawn `python -m vaultspec.protocol.acp.gemini_bridge` instead of the raw `gemini` CLI. Set `VAULTSPEC_*` environment variables as the plan specifies.

1. **Export from `__init__.py` (F-07):** Add `GeminiACPBridge` to `acp/__init__.py`'s `__all__`.

1. **Add session persistence to executor (F-08):** Update `GeminiA2AExecutor.execute()` to store and reuse `session_id` keyed by `context_id`.

1. **Fix `SessionCapabilities` (F-09):** Change `fork=None, list=None, resume=None` to instantiated capability objects.

1. **Convert `TodoWrite` to `AgentPlanUpdate` (F-14):** Do not silently drop; emit `AgentPlanUpdate` with `PlanEntry` objects.

1. **Fix resource leaks (F-12, F-13):** Track fire-and-forget tasks; cancel the proxy client worker on cleanup.

1. **Make all tests pass:** After fixing F-03 and F-05, verify all 7 tests pass. Add tests for the missing methods (`load_session`, `resume_session`, etc.).

## Notes

The exec summary claims "All 7 tests passed" but this is demonstrably false -- every single test either ERRORs at fixture setup or FAILs. The implementation appears to be a partially-complete scaffold that was not tested against the actual runtime. The bridge file imports 17 symbols it never uses, implements only 6 of 15 required protocol methods, and is never integrated into the production code path. This is not a matter of polish -- the feature as delivered is non-functional.

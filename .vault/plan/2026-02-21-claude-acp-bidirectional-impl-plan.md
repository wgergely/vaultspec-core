---
tags:
  - '#plan'
  - '#claude-acp-bidirectional'
date: '2026-02-21'
related:
  - '[[2026-02-21-claude-acp-bidirectional-adr]]'
  - '[[2026-02-21-claude-acp-bidirectional-reference]]'
  - '[[2026-02-21-protocol-gap-analysis-research]]'
  - '[[2026-02-21-acp-layer-audit-research]]'
---

# `claude-acp-bidirectional` implementation plan

Enable multi-turn bidirectional communication in the Claude ACP bridge by implementing
all six decisions from \[[2026-02-21-claude-acp-bidirectional-adr]\]. The work covers
session resume via Claude session ID, per-session state isolation, tool call content
accumulation with kind mapping, TodoWrite-to-plan conversion, non-destructive
abort/cancel, and a set of P0 bug fixes that the other changes depend on.

## Proposed Changes

The bridge (`src/vaultspec/protocol/acp/claude_bridge.py`, 988 lines) and client
(`src/vaultspec/protocol/acp/client.py`, 473 lines) are the primary targets. A
single A2A executor fix (`src/vaultspec/protocol/a2a/executors/claude_executor.py`)
addresses a thread-unsafe env var mutation discovered in the same audit.

The implementation follows the ADR's six decisions, reordered so that foundational
bug fixes land first (Phase 1), followed by structural changes (Phase 2-4), then
feature additions (Phase 5-6), and finally comprehensive tests (Phase 7).

All changes are additive to the ACP schema types already in use. Existing
`SubagentClient` callers will not break because new fields (`kind`, `content`,
`rawInput`) are optional on `ToolCallStart` and `ToolCallProgress`. The test
infrastructure (`SDKClientRecorder`, `ConnRecorder` in `conftest.py`) will be
extended -- not replaced -- to support the new per-session patterns.

## Tasks

### Phase 1: P0 Bug Fixes -- ADR Decision 6

Foundation fixes that all subsequent phases depend on. These are isolated,
low-risk corrections to confirmed bugs.

1. **Fix `on_connect()` no-op in client.py**

   - **What**: Store the `conn` argument in `self._conn` inside `on_connect()` so
     that `graceful_cancel()` at line 466-472 can actually send the cancel notification.
     Currently `on_connect()` is `pass` and `self._conn` stays `None` forever.

   - **Where**: `src/vaultspec/protocol/acp/client.py`, line 447-448

   - **Why**: ADR Decision 6, Fix 4. Gap analysis finding P1 #11.

   - **Tests**: Existing `SubagentClient` tests must verify that `on_connect()` stores
     the connection and that `graceful_cancel()` calls `conn.cancel()`.

1. **Fix exception masking -- differentiate error types**

   - **What**: Replace the broad `except Exception` at the end of the `prompt()`
     streaming loop with differentiated handling: `MessageParseError` is already
     handled (log and continue); remaining `Exception` should emit the error text as
     an `AgentMessageChunk` via `session_update` and return `"end_turn"` instead of
     `"refusal"`. Remove all uses of the non-standard `"refusal"` stop reason.

   - **Where**: `src/vaultspec/protocol/acp/claude_bridge.py`, lines 464-472
     (the `except` blocks in `prompt()`)

   - **Why**: ADR Decision 6, Fixes 5. Gap analysis findings P0 #2, P1 #9, P1 #12.

   - **Tests**: Update `test_bridge_resilience.py` -- existing tests that assert
     `stop_reason == "refusal"` must assert `"end_turn"` instead. Add a test that
     verifies the error text is emitted as `AgentMessageChunk` before the response.

1. **Fix non-standard stop reasons on `ResultMessage` errors**

   - **What**: In `prompt()` at line 464-466, when `ResultMessage.is_error` is True,
     return `"end_turn"` and emit the error text as `AgentMessageChunk`, instead of
     returning `"refusal"`. The ACP spec does not define `"refusal"` as a valid stop
     reason.

   - **Where**: `src/vaultspec/protocol/acp/claude_bridge.py`, lines 464-466

   - **Why**: ADR Decision 6, Fix 5. Gap analysis finding P1 #9.

   - **Tests**: Update any tests in `test_bridge_streaming.py` or
     `test_bridge_resilience.py` that check for `"refusal"` stop reason.

1. **Clear stale dicts between turns**

   - **What**: Clear `self._pending_tools` and `self._block_index_to_tool` at the
     start of each `prompt()` call, before the streaming loop begins. These dicts
     accumulate across turns and can cause incorrect tool correlation in long sessions.

   - **Where**: `src/vaultspec/protocol/acp/claude_bridge.py`, inside `prompt()`,
     after the cancel flag reset (around line 431)

   - **Why**: ADR Decision 6, Fix 6. Gap analysis finding P2 #18.

   - **Tests**: Add a test in `test_bridge_streaming.py` that runs two consecutive
     `prompt()` calls and verifies the dicts are empty at the start of the second call
     (no stale entries from the first call's tool uses).

1. **Fix CLAUDECODE env var mutation in A2A executor**

   - **What**: Replace `os.environ.pop("CLAUDECODE", None)` with a local env dict
     copy. Pass the modified copy to the SDK client via subprocess env isolation
     (the options factory or connect kwargs) instead of mutating the global
     `os.environ`. Restore is currently in a `finally` block but the mutation itself
     is thread-unsafe when multiple executors run concurrently.

   - **Where**: `src/vaultspec/protocol/a2a/executors/claude_executor.py`, lines 119-121

   - **Why**: ADR Decision 6, Fix 3. Gap analysis finding P0 #4.

   - **Tests**: The existing A2A executor tests must verify that `os.environ` is not
     mutated during `execute()`. Add a test that runs two executors concurrently and
     confirms neither sees the other's env mutation.

### Phase 2: Per-Session State and SDK Client -- ADR Decision 2

Restructure `_SessionState` and move from a single bridge-level `self._sdk_client`
to per-session clients, enabling state isolation as required by the ADR.

1. **Extend `_SessionState` with new fields**

   - **What**: Add four new fields to the `_SessionState` dataclass:
     `claude_session_id: str | None = None` (for Decision 1),
     `cancel_event: asyncio.Event` (for Decision 5, factory via `dataclasses.field`),
     `tool_call_contents: dict[str, list[dict]]` (for Decision 3, default empty dict),
     `todo_write_tool_call_ids: set[str]` (for Decision 4, default empty set).

   - **Where**: `src/vaultspec/protocol/acp/claude_bridge.py`, lines 148-159
     (`_SessionState` dataclass)

   - **Why**: ADR Decision 2. All four new fields are required by Decisions 1, 3, 4, 5.

   - **Tests**: Unit test that new `_SessionState` instances have correct defaults.

1. **Store SDK client in per-session state**

   - **What**: In `new_session()`, store the created `ClaudeSDKClient` in
     `state.sdk_client` in addition to `self._sdk_client`. Keep `self._sdk_client`
     as an alias to the active session's client for backward compatibility.

   - **Where**: `src/vaultspec/protocol/acp/claude_bridge.py`, `new_session()` at
     lines 384-401

   - **Why**: ADR Decision 2. The `_SessionState.sdk_client` field exists but is
     never populated.

   - **Tests**: Verify `state.sdk_client is bridge._sdk_client` after `new_session()`.

1. **Resolve SDK client from session state in `prompt()`**

   - **What**: At the start of `prompt()`, look up `self._sessions[session_id]` and
     use `state.sdk_client` for `query()` and `receive_response()`. Fall back to
     `self._sdk_client` if the session has no per-session client (backward compat).

   - **Where**: `src/vaultspec/protocol/acp/claude_bridge.py`, `prompt()` at
     lines 414-474

   - **Why**: ADR Decision 2. Required for per-session isolation.

   - **Tests**: Test that `prompt()` uses the session's client when available, not
     the bridge singleton.

1. **Update `load_session()` and `resume_session()` to store per-session client**

   - **What**: After rebuilding the SDK client in both methods, store it in
     `state.sdk_client` as well as `self._sdk_client`.

   - **Where**: `src/vaultspec/protocol/acp/claude_bridge.py`, `load_session()` at
     lines 553-554, `resume_session()` at lines 607-608

   - **Why**: ADR Decision 2.

   - **Tests**: Verify that after `load_session()`, the session state's `sdk_client`
     is the newly created client.

1. **Update `fork_session()` to use per-session client**

   - **What**: Store the new SDK client in the forked session's `state.sdk_client`.
     Remove any dead `self._stream` assignment if still present (ADR Decision 6, Fix 2).

   - **Where**: `src/vaultspec/protocol/acp/claude_bridge.py`, `fork_session()` at
     lines 619-673

   - **Why**: ADR Decisions 2 and 6 (Fix 2).

   - **Tests**: Verify forked session has its own `sdk_client` distinct from the
     source session.

1. **Update `SDKClientRecorder` in test conftest**

   - **What**: Make `interrupt()` an `async` method (to match the real SDK's async
     `interrupt()`). Add a `receive_response()` method that returns an
     `AsyncItemIterator` (currently only `receive_messages()` exists). These changes
     are prerequisites for all subsequent test phases.

   - **Where**: `src/vaultspec/protocol/acp/tests/conftest.py`, `SDKClientRecorder`
     class at lines 40-87

   - **Why**: ADR Constraints section -- `interrupt()` is async per SDK `client.py`
     line 219. Test infrastructure must match the real SDK's interface.

   - **Tests**: Self-verifying -- existing tests will exercise the updated recorder.

### Phase 3: Session Resume -- ADR Decision 1

Enable multi-turn conversations via Claude's native `session_id`. This is the
highest-impact change: without it, every `prompt()` starts a fresh conversation.

1. **Extract `session_id` from SDK messages in the streaming loop**

   - **What**: After each message from `receive_response()` in `prompt()`, check for
     a `session_id` attribute (present on `ResultMessage` and `StreamEvent` per SDK
     `types.py` lines 679, 691). If found and different from the stored value, update
     `state.claude_session_id`. The earliest extraction point is the first
     `StreamEvent`, matching the reference's `tryToStoreClaudeSessionId()` pattern.

   - **Where**: `src/vaultspec/protocol/acp/claude_bridge.py`, inside `prompt()`'s
     streaming loop (between line 451 and the `_emit_updates` call)

   - **Why**: ADR Decision 1. Gap analysis finding P0 #1.

   - **Tests**: Add test in `test_bridge_streaming.py` that feeds a `StreamEvent`
     with `session_id="sess_abc"` and verifies `state.claude_session_id` is updated.
     Add test with `ResultMessage` carrying `session_id`. Add test that the first
     extraction wins (subsequent identical values are no-ops).

1. **Pass `resume` parameter in `load_session()` and `resume_session()`**

   - **What**: After building options via `_build_options()`, set
     `options.resume = state.claude_session_id` if the stored value is not `None`.
     The SDK's `ClaudeAgentOptions` already supports `resume: str | None = None`
     at `types.py` line 725.

   - **Where**: `src/vaultspec/protocol/acp/claude_bridge.py`, `load_session()` at
     line 552 (after `_build_options`), `resume_session()` at line 606

   - **Why**: ADR Decision 1. This is what makes `load_session`/`resume_session`
     actually restore conversation history via Claude's server-side session.

   - **Tests**: Add test in `test_bridge_lifecycle.py` that: (a) creates a session,
     (b) runs a prompt that sets `claude_session_id`, (c) calls `load_session()`,
     (d) verifies the captured options include `resume="sess_abc"`. Same for
     `resume_session()`.

1. **Handle stale/expired sessions gracefully**

   - **What**: If `resume` fails (Claude rejects the session ID), the SDK will return
     an error `ResultMessage`. The `prompt()` error handling (updated in Phase 1, step 2)
     already emits this as `AgentMessageChunk` with `"end_turn"`. Additionally, clear
     `state.claude_session_id` when a resume error is detected so the next attempt
     starts fresh.

   - **Where**: `src/vaultspec/protocol/acp/claude_bridge.py`, in the error handling
     path of `prompt()` and `load_session()`/`resume_session()`

   - **Why**: ADR Consequences section -- "If Claude's backend evicts the session,
     `resume` will fail silently or error. We must handle this gracefully."

   - **Tests**: Add test that simulates a `ResultMessage(is_error=True)` after a
     `load_session()` with `resume`, and verifies `claude_session_id` is cleared.

### Phase 4: Abort/Cancel Pattern -- ADR Decision 5

Replace the global `self._cancelled` boolean with per-session cancellation using
`asyncio.Event`. Make `cancel()` non-destructive -- interrupt the stream but keep
the session alive for future prompts.

1. **Replace `self._cancelled` with per-session `cancel_event`**

   - **What**: Remove the bridge-level `self._cancelled: bool = False` attribute.
     In `prompt()`, use `state.cancel_event.is_set()` instead of `self._cancelled`.
     At the start of `prompt()`, call `state.cancel_event.clear()`. In the `finally`
     block, clear the event if still set.

   - **Where**: `src/vaultspec/protocol/acp/claude_bridge.py`, constructor (line 270),
     `prompt()` (lines 431, 458-460)

   - **Why**: ADR Decision 5. The boolean flag is not per-session and has no
     synchronization.

   - **Tests**: Update `test_bridge_resilience.py::TestCancelTracking` -- replace all
     assertions on `bridge._cancelled` with assertions on the session state's
     `cancel_event`. Add test that cancelling session A does not affect session B.

1. **Fix `cancel()` to use per-session client and async `interrupt()`**

   - **What**: Resolve the SDK client from `self._sessions[session_id].sdk_client`
     instead of `self._sdk_client`. Call `await state.sdk_client.interrupt()` (add
     the missing `await`). Do NOT call `disconnect()` -- the client remains alive
     for future turns. Do NOT set `state.connected = False`.

   - **Where**: `src/vaultspec/protocol/acp/claude_bridge.py`, `cancel()` at
     lines 476-491

   - **Why**: ADR Decision 5. Gap analysis findings P0 #2 (missing await),
     P0 #3 (destructive cancel).

   - **Tests**: Update `test_bridge_resilience.py::TestCancel` -- verify that after
     `cancel()`, `state.connected` is still `True`, `disconnect()` was NOT called,
     and `interrupt()` was called with `await`. Add test that a subsequent `prompt()`
     call succeeds after `cancel()` without needing `load_session()`.

1. **Remove `disconnect()` from cancel flow**

   - **What**: The `cancel()` method currently calls `self._sdk_client.disconnect()`
     which kills the entire subprocess. Remove this call entirely. The session remains
     valid and the client can accept new `query()` calls.

   - **Where**: `src/vaultspec/protocol/acp/claude_bridge.py`, `cancel()` at
     lines 484-487

   - **Why**: ADR Decision 5. Reference pattern: `AbortController` per session at
     `agent.ts:325-337` -- cancel does not destroy the session.

   - **Tests**: Verify `sdk_client.disconnect_count == 0` after `cancel()`.

### Phase 5: Tool Call Content and Kind Mapping -- ADR Decision 3

Enrich tool call events with `kind`, `content`, and `rawInput` fields. Maintain
per-session content accumulation across the tool lifecycle.

1. **Add `_map_tool_kind()` utility function**

   - **What**: Add a module-level function that maps tool names to ACP `kind` values
     using substring matching on the lowercased tool name. Mapping:
     `read/view/get` -> `"read"`, `write/create/update/edit` -> `"edit"`,
     `delete/remove` -> `"delete"`, `move/rename` -> `"move"`,
     `search/find/grep` -> `"search"`, `run/execute/bash` -> `"execute"`,
     `think/plan` -> `"think"`, `fetch/download` -> `"fetch"`, else -> `"other"`.

   - **Where**: `src/vaultspec/protocol/acp/claude_bridge.py`, new function near the
     top of the module (after `_extract_prompt_text`)

   - **Why**: ADR Decision 3. Reference pattern: `mapToolKind()` at `agent.ts:663-711`.

   - **Tests**: Add `test_tool_kind_mapping.py` (or section in `test_bridge_streaming.py`)
     with parametrized tests covering each keyword category and the `"other"` fallback.

1. **Add `_get_tool_call_content()` for Edit/MultiEdit diff blocks**

   - **What**: Add a module-level function that takes a tool name and tool input dict,
     and returns a list of content dicts. For `Edit` tool: if input has `file_path`,
     `old_string`, `new_string`, return `[{"type": "diff", "path": ..., "oldText": ..., "newText": ...}]`.
     For `MultiEdit`: if input has `file_path` and `edits`, return one diff block per
     edit entry. For all other tools, return empty list.

   - **Where**: `src/vaultspec/protocol/acp/claude_bridge.py`, new function near
     `_map_tool_kind()`

   - **Why**: ADR Decision 3. Reference pattern: `getToolCallContent()` at
     `agent.ts:713-744`.

   - **Tests**: Parametrized tests for Edit, MultiEdit (single and multiple edits),
     and non-edit tools (returns empty list).

1. **Emit enriched `ToolCallStart` in `_emit_assistant()`**

   - **What**: On `ToolUseBlock`, call `_get_tool_call_content(block.name, block.input)`
     to produce initial content. Store in `state.tool_call_contents[block.id]`. Emit
     `ToolCallStart` with `kind=_map_tool_kind(block.name)`,
     `content=state.tool_call_contents[block.id]`, and `raw_input=block.input`.

   - **Where**: `src/vaultspec/protocol/acp/claude_bridge.py`, `_emit_assistant()` at
     lines 875-886

   - **Why**: ADR Decision 3.

   - **Tests**: Update `test_bridge_streaming.py` tests for `_emit_assistant()` to
     verify `kind`, `content`, and `raw_input` fields on `ToolCallStart`. Add
     specific test for Edit tool producing diff content blocks.

1. **Emit enriched `ToolCallProgress` in `_emit_user_message()`**

   - **What**: On tool result, extract text content from `ToolResultBlock` content
     blocks, append to `state.tool_call_contents[tool_use_id]` as
     `{"type": "content", "content": {"type": "text", "text": ...}}`. Emit
     `ToolCallProgress` with `content=state.tool_call_contents[tool_use_id]`.

   - **Where**: `src/vaultspec/protocol/acp/claude_bridge.py`, `_emit_user_message()`
     at lines 897-936

   - **Why**: ADR Decision 3.

   - **Tests**: Add test that runs a full tool lifecycle (ToolUseBlock ->
     UserMessage with ToolResultBlock) and verifies content accumulation on the
     ToolCallProgress event.

### Phase 6: TodoWrite-to-Plan Conversion -- ADR Decision 4

Intercept TodoWrite tool calls and convert them to ACP `AgentPlanUpdate` events.
Suppress TodoWrite from normal tool call events.

1. **Intercept TodoWrite in `_emit_assistant()`**

   - **What**: On `ToolUseBlock` where `block.name == "TodoWrite"`, extract `todos`
     from `block.input`, build an `AgentPlanUpdate` with mapped entries, emit via
     `session_update`. Add `block.id` to `state.todo_write_tool_call_ids`. Do NOT
     emit `ToolCallStart` for this block.

   - **Where**: `src/vaultspec/protocol/acp/claude_bridge.py`, `_emit_assistant()` at
     lines 875-886 (before the existing `ToolUseBlock` handling)

   - **Why**: ADR Decision 4. Reference pattern: `sendAgentPlan()` at `agent.ts:685-711`.

   - **Tests**: Add test that feeds an `AssistantMessage` with a TodoWrite
     `ToolUseBlock` and verifies: (a) `AgentPlanUpdate` is emitted, (b) `ToolCallStart`
     is NOT emitted, (c) block.id is in `state.todo_write_tool_call_ids`.

1. **Intercept TodoWrite in `_emit_stream_event()`**

   - **What**: On `content_block_start` with `tool_use` type where tool name is
     `"TodoWrite"`, emit `AgentPlanUpdate` from partial input if the `todos` field
     is present. Track the tool call ID in `state.todo_write_tool_call_ids`.

   - **Where**: `src/vaultspec/protocol/acp/claude_bridge.py`, `_emit_stream_event()`
     at lines 809-815 (inside the `content_block_start` handling)

   - **Why**: ADR Decision 4. Reference intercepts at both `tool_use_start` and
     `assistant` message.

   - **Tests**: Add test with a `StreamEvent` containing a TodoWrite
     `content_block_start` and verify `AgentPlanUpdate` emission.

1. **Suppress TodoWrite from `_emit_user_message()`**

   - **What**: If `tool_use_id` is in `state.todo_write_tool_call_ids`, skip emitting
     `ToolCallProgress`. The plan update was already sent in `_emit_assistant()`.

   - **Where**: `src/vaultspec/protocol/acp/claude_bridge.py`, `_emit_user_message()`
     at lines 904-906 (early return check)

   - **Why**: ADR Decision 4.

   - **Tests**: Add test that feeds a `UserMessage` with a `parent_tool_use_id` in
     `state.todo_write_tool_call_ids` and verifies no `ToolCallProgress` is emitted.

1. **Import `AgentPlanUpdate` in bridge module**

   - **What**: Add `AgentPlanUpdate` to the `acp.schema` import block at the top of
     `claude_bridge.py`. It is already available in the `acp` package (confirmed
     by its existing import in `client.py` at line 17).

   - **Where**: `src/vaultspec/protocol/acp/claude_bridge.py`, import block at
     lines 34-56

   - **Why**: Required by steps 1-3 above.

   - **Tests**: No separate test -- validated by the TodoWrite emission tests.

### Phase 7: Tests

New and updated tests covering all phases. Tests must use DI-injected recorders
per the project's no-mocking rule. No `unittest.mock`, `pytest-mock`, or `monkeypatch`.

1. **Update `SDKClientRecorder` and `ConnRecorder` in conftest**

   - **What**: (a) Make `SDKClientRecorder.interrupt()` async. (b) Add
     `receive_response()` method. (c) Add `session_id` attribute support on
     test message types. (d) Extend `ConnRecorder.session_update_calls` to capture
     the full update object for field-level assertions.

   - **Where**: `src/vaultspec/protocol/acp/tests/conftest.py`

   - **Why**: Prerequisites for all new tests.

   - **Executing sub-agent**: `vaultspec-standard-executor`

1. **Multi-turn session resume tests**

   - **What**: Tests that exercise the full session resume lifecycle:
     (a) create session -> prompt -> extract session_id -> second prompt (same client),
     (b) create session -> prompt -> load_session -> verify resume in options,
     (c) create session -> prompt -> resume_session -> verify resume in options,
     (d) stale session_id handling (error on resume -> cleared -> fresh session).

   - **Where**: New test class `TestSessionResume` in `test_bridge_lifecycle.py`

   - **Why**: ADR Decision 1. Gap analysis finding P1 #10.

1. **Per-session state isolation tests**

   - **What**: Tests that verify: (a) two concurrent sessions have independent
     `cancel_event`, `tool_call_contents`, `todo_write_tool_call_ids`,
     (b) cancelling one session does not affect the other,
     (c) `_pending_tools` and `_block_index_to_tool` are cleared between turns.

   - **Where**: New test class `TestSessionIsolation` in `test_bridge_lifecycle.py`

   - **Why**: ADR Decision 2.

1. **Cancel/abort non-destructive tests**

   - **What**: Tests that verify: (a) `cancel()` calls `await interrupt()` (not sync),
     (b) `cancel()` does NOT call `disconnect()`,
     (c) session remains `connected=True` after cancel,
     (d) subsequent `prompt()` succeeds after cancel without `load_session()`.

   - **Where**: Update `TestCancel` and `TestCancelTracking` in
     `test_bridge_resilience.py`

   - **Why**: ADR Decision 5.

1. **Tool kind mapping tests**

   - **What**: Parametrized tests for `_map_tool_kind()` covering all keyword
     categories: Read, Edit, Write, Bash, Grep, Search, Think, TodoWrite,
     WebFetch, and unknown tools. Verify case-insensitive matching.

   - **Where**: New test class or section in `test_bridge_streaming.py`

   - **Why**: ADR Decision 3.

1. **Content accumulation tests**

   - **What**: Tests for the full tool lifecycle:
     (a) `ToolUseBlock(name="Edit")` -> `ToolCallStart` with diff content,
     (b) `UserMessage` with `ToolResultBlock` -> `ToolCallProgress` with accumulated
     content (initial diff + result text),
     (c) `MultiEdit` with multiple edits -> multiple diff blocks in content array.

   - **Where**: New test class `TestContentAccumulation` in `test_bridge_streaming.py`

   - **Why**: ADR Decision 3.

1. **TodoWrite plan conversion tests**

   - **What**: Tests that verify:
     (a) `AssistantMessage` with TodoWrite `ToolUseBlock` emits `AgentPlanUpdate`,
     (b) TodoWrite `ToolUseBlock` is suppressed from `ToolCallStart`,
     (c) `UserMessage` with TodoWrite `parent_tool_use_id` is suppressed from
     `ToolCallProgress`,
     (d) `StreamEvent` with TodoWrite `content_block_start` emits `AgentPlanUpdate`.

   - **Where**: New test class `TestTodoWritePlan` in `test_bridge_streaming.py`

   - **Why**: ADR Decision 4.

1. **Error stop reason tests**

   - **What**: Tests that verify: (a) `ResultMessage(is_error=True)` returns
     `"end_turn"` not `"refusal"`, (b) generic exceptions return `"end_turn"` with
     error text as `AgentMessageChunk`, (c) `MessageParseError` is logged and
     skipped (does not change stop reason).

   - **Where**: Update existing tests in `test_bridge_resilience.py`

   - **Why**: ADR Decision 6, Fix 5.

1. **E2E multi-turn test (gated)**

   - **What**: A gated integration test (`@pytest.mark.claude`) that exercises the
     full multi-turn flow with a real Claude SDK: create session -> prompt -> verify
     session_id extracted -> second prompt -> verify conversation continuity.

   - **Where**: `src/vaultspec/protocol/acp/tests/test_e2e_bridge.py` or
     `tests/e2e/test_acp_multiturn_e2e.py`

   - **Why**: ADR Decision 1. Gap analysis finding P1 #10.

## Parallelization

The phases have the following dependency structure:

```
Phase 1 (Bug Fixes)
   |
   +---> Phase 2 (Per-Session State)
   |        |
   |        +---> Phase 3 (Session Resume)
   |        |
   |        +---> Phase 4 (Abort/Cancel)
   |        |
   |        +---> Phase 5 (Tool Content)
   |        |
   |        +---> Phase 6 (TodoWrite)
   |
   +---> Phase 1, Step 5 (A2A env fix -- independent)
```

- **Phase 1** must complete first -- it fixes bugs that Phase 2-6 depend on.

- **Phase 1, Step 5** (A2A executor env var fix) is independent and can run in
  parallel with everything else.

- **Phase 2** must complete before Phases 3, 4, 5, 6 because they all depend on
  the extended `_SessionState` and per-session SDK client.

- **Phases 3, 4, 5, 6** are mutually independent after Phase 2 completes and can
  run in parallel. They touch different methods and fields:

  - Phase 3: `prompt()` streaming loop (session_id extraction), `load_session()`,
    `resume_session()`.

  - Phase 4: `cancel()`, `prompt()` cancel checking.

  - Phase 5: `_emit_assistant()`, `_emit_user_message()`, new utility functions.

  - Phase 6: `_emit_assistant()`, `_emit_stream_event()`, `_emit_user_message()`
    (TodoWrite-specific paths).

  - **Caveat**: Phases 5 and 6 both modify `_emit_assistant()`. If running in
    parallel, coordinate merge carefully -- Phase 6 adds a TodoWrite check before
    Phase 5's enriched `ToolCallStart`.

- **Phase 7** (tests) should run after its corresponding implementation phase.
  Test steps 1 (conftest update) should run with Phase 2. Steps 2-9 can run as
  each implementation phase completes.

**Recommended execution plan for sub-agents:**

- **Wave 1**: Phase 1 (all steps) + Phase 1 Step 5 (parallel)
- **Wave 2**: Phase 2 (all steps) + Phase 7 Step 1 (conftest)
- **Wave 3**: Phases 3, 4, 5, 6 (parallel, 4 sub-agents) + corresponding Phase 7 tests
- **Wave 4**: Phase 7 Step 9 (E2E test, after all implementation complete)

## Verification

Success criteria tied to each ADR decision:

**Decision 1 -- Session Resume**: `state.claude_session_id` is populated after
the first `prompt()` call. `load_session()` and `resume_session()` pass `resume`
in the captured options. Unit tests verify extraction from both `StreamEvent` and
`ResultMessage`.

**Decision 2 -- Per-Session State**: `state.sdk_client` is populated and used by
`prompt()`. Two sessions have independent state objects. `_pending_tools` and
`_block_index_to_tool` are cleared between turns.

**Decision 3 -- Tool Content**: `ToolCallStart` includes `kind`, `content`, and
`raw_input`. Edit tools produce diff content blocks. Content accumulates across
the tool lifecycle and is sent with `ToolCallProgress`.

**Decision 4 -- TodoWrite-to-Plan**: TodoWrite `ToolUseBlock` emits
`AgentPlanUpdate`, not `ToolCallStart`. TodoWrite `UserMessage` does not emit
`ToolCallProgress`. The `todo_write_tool_call_ids` set correctly tracks IDs.

**Decision 5 -- Abort/Cancel**: `cancel()` calls `await interrupt()` (async).
`cancel()` does NOT call `disconnect()`. `state.connected` remains `True`.
Subsequent `prompt()` succeeds without `load_session()`. Per-session cancel does
not affect other sessions.

**Decision 6 -- Bug Fixes**: `on_connect()` stores `conn`. No `"refusal"` stop
reason anywhere. Dicts cleared between turns. CLAUDECODE env not mutated globally.
`MessageParseError` logged and skipped.

**Overall**: All existing tests in `test_bridge_lifecycle.py`,
`test_bridge_streaming.py`, and `test_bridge_resilience.py` pass after updates.
No mocks introduced. All new tests use DI-injected recorders. The gated E2E test
passes against a real Claude SDK (manual verification, `@pytest.mark.claude`).

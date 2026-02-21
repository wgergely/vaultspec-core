---
tags:
  - "#adr"
  - "#claude-acp-bidirectional"
date: "2026-02-21"
related:
  - "[[2026-02-21-claude-acp-bidirectional-reference]]"
  - "[[2026-02-21-protocol-gap-analysis-research]]"
  - "[[2026-02-21-acp-layer-audit-research]]"
  - "[[2026-02-21-acp-ref-impl-research]]"
---

# `claude-acp-bidirectional` adr: `Multi-Turn Bidirectional Communication in Claude ACP Bridge` | (**status:** `accepted`)

## Problem Statement

The Claude ACP bridge (`src/vaultspec/protocol/acp/claude_bridge.py`) cannot sustain multi-turn conversations. Every `prompt()` call starts a fresh conversation context because we never extract Claude's native `session_id` from SDK messages and never pass it as a `resume` parameter on subsequent queries. The cancel mechanism is global (a single `self._cancelled` boolean), destructive (kills the entire SDK client), and contains async bugs (missing `await` on coroutines). Tool call events are emitted without `kind`, `content`, or `rawInput` fields, making rich client rendering impossible. TodoWrite tool calls are not intercepted for ACP plan updates. Several confirmed bugs -- dead stream references, stale dictionaries, non-standard stop reasons, and a no-op `on_connect()` in the client -- compound these issues.

The [[2026-02-21-protocol-gap-analysis-research]] identified 19 findings across both protocol layers. This ADR addresses the 14 findings that apply to the ACP bridge specifically, organized into six architectural decisions.

## Considerations

### Reference Architecture

The primary reference is `acp-claude-code` (github.com/Xuanwo/acp-claude-code, v0.8.0), a TypeScript ACP bridge for Claude Code with 235 stars. Full analysis in [[2026-02-21-acp-ref-impl-research]]. Key architectural patterns extracted in [[2026-02-21-claude-acp-bidirectional-reference]]:

- **Stateless `query()` per turn**: The reference creates a fresh `query()` invocation per `prompt()` call and achieves multi-turn via `resume: session.claudeSessionId`. Our Python SDK uses a persistent `ClaudeSDKClient` subprocess instead. Both approaches need `session_id` extraction, but ours also needs it for `load_session`/`resume_session` client recreation.

- **Per-session state isolation**: The reference stores all mutable state in a `sessions: Map<string, AgentSession>` with per-session `AbortController`, `pendingPrompt`, `toolCallContents`, and `todoWriteToolCallIds`. Our bridge uses bridge-level singletons (`self._cancelled`, `self._pending_tools`, `self._block_index_to_tool`).

- **Tool call content accumulation**: The reference maintains a `toolCallContents: Map<string, ACPToolCallContent[]>` per session that accumulates content blocks across the tool lifecycle (start, output, result). Every update sends the full accumulated array. We send only `status` on completion, with no content.

- **TodoWrite interception**: The reference intercepts TodoWrite at both `tool_use_start` (streaming) and `assistant` (complete message), converts to `AgentPlanUpdate`, and suppresses from tool call events. We do not handle TodoWrite at all.

### SDK Differences

The Python `claude-agent-sdk` and TypeScript `@anthropic-ai/claude-code` SDK are architecturally different:

- The TypeScript SDK exports a stateless `query()` function returning `AsyncIterable<SDKMessage>`. The Python SDK provides `ClaudeSDKClient` with a persistent subprocess, `connect()`, `query()`, and `receive_response()`.
- The TypeScript SDK emits fine-grained types (`tool_use_start`, `tool_use_output`, `tool_use_error`, `text`). The Python SDK consolidates these into `StreamEvent`, `AssistantMessage`, `UserMessage`, and `ResultMessage`. The mapping is 1:1, but extraction requires different field access patterns (see reference audit, Section 3.3 in [[2026-02-21-claude-acp-bidirectional-reference]]).
- Both SDKs carry `session_id` on `ResultMessage` and `StreamEvent` (Python SDK `types.py` lines 679, 691). Both SDKs support `resume` on `ClaudeAgentOptions` (Python SDK `types.py` line 725).

### Our Current Architecture

Audited in [[2026-02-21-acp-layer-audit-research]]. Key issues:

- `_SessionState` (line 148-159) stores config but no Claude session ID, no per-session cancel state, no tool call content tracking.
- `prompt()` (line 414-474) calls `self._sdk_client.query()` then iterates `receive_response()`. Never extracts `session_id`. Uses global `self._cancelled`. Returns non-standard `"refusal"` stop reason on errors.
- `cancel()` (line 476-491) sets global `self._cancelled`, calls `interrupt()` and `disconnect()` synchronously (both are `async` -- confirmed bug), and kills the entire SDK client.
- `load_session()` (line 512-565) and `resume_session()` (line 567-617) rebuild the SDK client from stored config but never pass `resume`, so conversation history is lost.
- `_emit_assistant()` (line 863-896) emits `ToolCallStart` with only `title` and `status`. No `kind`, `content`, or `rawInput`.
- `_emit_user_message()` (line 897-936) emits `ToolCallProgress` with only `status`. No accumulated content.
- `fork_session()` (line 619-673) creates a dead `self._stream` reference (line 657 -- removed in latest, but still tracked as a known pattern).

## Constraints

- **Upstream SDK immutability**: We cannot modify the `claude-agent-sdk` package. The `rate_limit_event` parse bug (`MessageParseError: Unknown message type: rate_limit_event` at `message_parser.py:180`) remains. Our streaming loop must catch `MessageParseError` and continue gracefully.

- **Backward compatibility**: `SubagentClient` (`src/vaultspec/protocol/acp/client.py`) callers depend on the current `session_update()` callback signatures. New fields (`kind`, `content`, `rawInput`) must be additive -- existing callers must not break.

- **No mocks in tests**: All testing must use DI-injected recorders (`SDKClientRecorder`, `ConnRecorder`) as established in `test_bridge_lifecycle.py`, `test_bridge_streaming.py`, and `test_bridge_resilience.py`. No `unittest.mock`, `pytest-mock`, or `monkeypatch`.

- **Python SDK architecture**: The Python SDK's `ClaudeSDKClient` maintains a persistent subprocess. We cannot adopt the reference's "fresh `query()` per turn" pattern directly. We use `client.query(prompt)` then `client.receive_response()`. Session resume via `resume` is needed only when recreating the client (in `load_session`/`resume_session`), not on every turn.

- **First of six protocol cases**: This is the Claude ACP subagent case. Decisions here set precedent for Claude ACP team, Claude A2A subagent, Claude A2A team, Gemini A2A subagent, and Gemini A2A team. Patterns must be generalizable.

- **Concurrent sessions**: The reference supports multiple concurrent sessions via its `sessions: Map`. Our single `self._sdk_client` prevents this. Moving to per-session SDK clients is required for concurrent session support but is architecturally significant. This ADR scopes per-session client storage but does not require concurrent prompt execution in the first implementation phase.

## Implementation

Six decisions, ordered by priority. Each references specific patterns from [[2026-02-21-claude-acp-bidirectional-reference]] and findings from [[2026-02-21-protocol-gap-analysis-research]].

### Decision 1: Session Resume via Claude Session ID

**Gap analysis finding**: P0 #1 -- "No Session Resume in ACP Bridge (CRITICAL)"

Extract `session_id` from SDK messages during the streaming loop and store it in `_SessionState`. Pass it as the `resume` parameter when rebuilding the SDK client in `load_session()` and `resume_session()`.

**What changes in `_SessionState`** (currently at `claude_bridge.py` line 148):

- Add `claude_session_id: str | None = None` field.

**What changes in `prompt()`** (currently at `claude_bridge.py` line 414):

- After each message from `receive_response()`, check for `session_id` attribute (present on `ResultMessage` at SDK `types.py:679` and `StreamEvent` at SDK `types.py:691`).
- If found and different from stored value, update `state.claude_session_id`.
- The earliest extraction point is the first `StreamEvent`, matching the reference's `tryToStoreClaudeSessionId()` pattern (reference `agent.ts` lines 746-764).

**What changes in `load_session()` and `resume_session()`** (currently at `claude_bridge.py` lines 512, 567):

- After building options via `_build_options()`, set `options.resume = state.claude_session_id` if the stored value is not `None`.
- The Python SDK's `ClaudeAgentOptions` already supports `resume: str | None = None` (SDK `types.py` line 725). We never use it today.

**Reference pattern**: `tryToStoreClaudeSessionId()` at `agent.ts:746-764` checks every SDK message for a `session_id` field and stores it in `session.claudeSessionId`. On subsequent `query()` calls, it passes `resume: session.claudeSessionId || undefined`.

### Decision 2: Per-Session SDK Client Management

**Gap analysis finding**: P2 #17 -- "Per-Session SDK Clients in ACP Bridge"

Move from a single `self._sdk_client` to per-session clients stored in `self._sessions[id].sdk_client`. The `_SessionState` dataclass already has an `sdk_client` field (line 158) that is never used.

**What changes**:

- `new_session()`: Store the created `ClaudeSDKClient` in `state.sdk_client` instead of (or in addition to) `self._sdk_client`. Keep `self._sdk_client` as an alias to the active session's client for backward compatibility during the transition.
- `prompt()`: Resolve the SDK client from `self._sessions[session_id].sdk_client` rather than `self._sdk_client`.
- `cancel()`: Resolve the SDK client from the session, not the bridge singleton.
- `load_session()` / `resume_session()`: Store the rebuilt client in `state.sdk_client`.

**Reference pattern**: `sessions: Map<string, AgentSession>` at `agent.ts` lines 91-99. Each session owns its own state. The `prompt()` method resolves session by `params.sessionId`.

### Decision 3: Tool Call Content Accumulation and Kind Mapping

**Gap analysis findings**: P1 #14 -- "No Tool Kind Mapping", P2 #13 -- implicit in content handling, P3 -- "Structured diff content"

Maintain a `tool_call_contents: dict[str, list[dict]]` per session. Populate it at tool start (with diff blocks for Edit/MultiEdit), accumulate on tool output/result, and send the full array with every `ToolCallStart` and `ToolCallProgress` update. Map tool names to ACP `kind` values using substring matching.

**What changes in `_SessionState`**:

- Add `tool_call_contents: dict[str, list[dict]]` field (default: empty dict).

**What changes in `_emit_assistant()`** (currently at `claude_bridge.py` line 863):

- On `ToolUseBlock`: call `_get_tool_call_content(block.name, block.input)` to produce initial content (diff blocks for Edit/MultiEdit, empty for others). Store in `state.tool_call_contents[block.id]`.
- Emit `ToolCallStart` with `kind=_map_tool_kind(block.name)`, `content=state.tool_call_contents[block.id]`, and `raw_input=block.input`.

**What changes in `_emit_user_message()`** (currently at `claude_bridge.py` line 897):

- On tool result: extract text content from `ToolResultBlock`, append to `state.tool_call_contents[tool_use_id]`.
- Emit `ToolCallProgress` with `content=state.tool_call_contents[tool_use_id]` and `raw_output` from the result.

**Kind mapping** follows the reference's `mapToolKind()` at `agent.ts:663-711`:

- `read/view/get` -> `"read"`, `write/create/update/edit` -> `"edit"`, `delete/remove` -> `"delete"`, `move/rename` -> `"move"`, `search/find/grep` -> `"search"`, `run/execute/bash` -> `"execute"`, `think/plan` -> `"think"`, `fetch/download` -> `"fetch"`, else -> `"other"`.

**Diff content extraction** follows the reference's `getToolCallContent()` at `agent.ts:713-744`:

- `Edit` tool: if input has `file_path`, `old_string`, `new_string`, emit `{"type": "diff", "path": ..., "oldText": ..., "newText": ...}`.
- `MultiEdit` tool: if input has `file_path` and `edits`, emit one diff block per edit.

### Decision 4: TodoWrite-to-Plan Conversion

**Gap analysis finding**: P2 #13 -- "No TodoWrite-to-Plan Conversion in ACP"

Intercept TodoWrite tool calls at two points and convert to ACP `AgentPlanUpdate`. Suppress TodoWrite from tool call events.

**What changes in `_SessionState`**:

- Add `todo_write_tool_call_ids: set[str]` field (default: empty set).

**What changes in `_emit_assistant()`**:

- On `ToolUseBlock` where `block.name == "TodoWrite"`: extract `todos` from `block.input`, build `AgentPlanUpdate` with mapped entries, emit via `session_update`. Add `block.id` to `state.todo_write_tool_call_ids`. Do NOT emit `ToolCallStart`.

**What changes in `_emit_user_message()`**:

- If `tool_use_id` is in `state.todo_write_tool_call_ids`: skip emitting `ToolCallProgress`. The plan update was already sent.

**What changes in `_emit_stream_event()`**:

- On `content_block_start` with `tool_use` type where tool name is `"TodoWrite"`: emit `AgentPlanUpdate` from partial input if `todos` is available. Track the tool call ID.

**Reference pattern**: `sendAgentPlan()` at `agent.ts:685-711` intercepts at both `tool_use_start` and `assistant` message. `todoWriteToolCallIds: Set<string>` tracks IDs for suppression at `tool_use_output`.

### Decision 5: Abort/Cancel Pattern

**Gap analysis findings**: P0 #2 -- "`cancel()` Missing `await`", P0 #3 -- "Dead `self._stream` in `fork_session()`"

Replace the global `self._cancelled` boolean with per-session cancellation. Do not disconnect the SDK client on cancel -- only interrupt the current stream. The session remains valid for future prompts.

**What changes in `_SessionState`**:

- Add `cancel_event: asyncio.Event` field. Set on cancel, checked in the streaming loop, cleared at the start of each `prompt()`.

**What changes in `cancel()`** (currently at `claude_bridge.py` line 476):

- Resolve session state from `self._sessions[session_id]`.
- Set `state.cancel_event.set()`.
- Call `await state.sdk_client.interrupt()` (fix: add `await` -- `interrupt()` is async per SDK `client.py` line 219).
- Do NOT call `disconnect()`. The client remains alive for future turns.
- Do NOT modify `state.connected`.

**What changes in `prompt()`**:

- At start: `state.cancel_event.clear()` (replaces `self._cancelled = False`).
- In streaming loop: check `state.cancel_event.is_set()` (replaces `self._cancelled`).
- In finally block: clear `state.cancel_event` if still set.

**What this fixes**:

- `interrupt()` is called with `await` (was sync -- confirmed bug at line 481).
- `disconnect()` is no longer called on cancel (was killing the client, requiring full reconnect).
- Cancel is per-session (was global, would affect all sessions).
- Session survives cancel and is ready for the next `prompt()` call.

**Reference pattern**: `AbortController` per session at `agent.ts:325-337`. `cancel()` calls `session.abortController.abort()` then `session.pendingPrompt.return()`. Session stays in the map with `claudeSessionId` preserved.

### Decision 6: P0/P1 Bug Fixes

These are standalone fixes that do not require architectural decisions but must ship with this work.

**Fix 1**: `cancel()` missing `await` on `disconnect()` -- addressed by Decision 5 (disconnect removed entirely).

**Fix 2**: Dead `self._stream` in `fork_session()` at line 657 -- remove the dead assignment. `prompt()` uses `receive_response()`, not a persistent stream.

**Fix 3**: `CLAUDECODE` env var mutation at `src/vaultspec/protocol/a2a/executors/claude_executor.py:121` -- use `env=os.environ.copy()` with modifications instead of mutating `os.environ` directly. This is thread-unsafe. (Note: this is in the A2A executor, not the ACP bridge, but is P0 and was identified in the same audit.)

**Fix 4**: `on_connect()` no-op in `client.py` at line 447 -- store `conn` in `self._conn` so that `graceful_cancel()` at line 466-472 can actually send the cancel notification.

**Fix 5**: Broad exception catch masking error types at `claude_bridge.py` line 470-472 -- differentiate `MessageParseError` (recoverable, log and continue) from other exceptions (emit error as `AgentMessageChunk`, return `"end_turn"` not `"refusal"`). The `"refusal"` stop reason is non-standard per ACP spec (finding P1 #9).

**Fix 6**: `_block_index_to_tool` and `_pending_tools` never cleared between turns at `claude_bridge.py` lines 263-267 -- clear both dictionaries at the start of each `prompt()` call.

## Rationale

### Why Persistent Client + Resume (not Stateless Query per Turn)

The Python `claude-agent-sdk` is designed around `ClaudeSDKClient` with a persistent subprocess. The reference's "fresh `query()` per turn" pattern works because the TypeScript SDK's `query()` is a standalone function. Attempting to create and destroy `ClaudeSDKClient` instances per turn would add subprocess spawn latency (~200-500ms on Windows) and lose the benefit of persistent `can_use_tool` callbacks. We keep the persistent client for normal multi-turn flow and use `resume` only for client recreation in `load_session`/`resume_session`.

This was validated by examining the Python SDK's `ClaudeSDKClient.connect()` (subprocess spawn) vs `query()` (message send over existing pipe). The cost asymmetry makes persistent clients the correct choice.

### Why Per-Session State (not Bridge-Level Singletons)

The reference's `sessions: Map<string, AgentSession>` pattern is the correct isolation boundary. Our current bridge-level `self._cancelled`, `self._pending_tools`, and `self._block_index_to_tool` break as soon as a second session exists. Even without concurrent sessions, `fork_session()` creates a second session that shares these singletons. Moving to per-session state is a prerequisite for correctness, not just concurrency.

### Why `asyncio.Event` for Cancellation (not Boolean Flag)

`asyncio.Event` is the standard asyncio primitive for cross-coroutine signaling. It is awaitable (useful for future timeout patterns), thread-safe via the event loop, and semantically clear. The boolean `self._cancelled` has no synchronization and is not per-session.

### Why Content Accumulation (not Status-Only Updates)

The ACP protocol supports `content` on `ToolCallStart` and `ToolCallProgress` for exactly this purpose -- rich clients (like Zed) render tool call details including diffs, file paths, and output. Sending only `status` wastes the protocol's expressiveness and forces clients to make separate queries for tool details. The reference's accumulation pattern is simple (append to a list per tool call ID) and adds minimal overhead.

### Why TodoWrite Interception (not Passthrough)

TodoWrite is a Claude-internal tool that creates a structured plan. Passing it through as a generic tool call is meaningless to ACP clients. Converting to `AgentPlanUpdate` enables Zed's plan panel and other rich UIs. The suppression pattern (tracking IDs, skipping at output) is minimal and follows the reference exactly.

### Why `"end_turn"` on Errors (not `"refusal"`)

The ACP spec defines `end_turn`, `cancelled`, `max_tokens`, and `tool_use` as valid stop reasons. `"refusal"` is not in the spec. The reference always returns `"end_turn"` on errors and emits the error text as an `AgentMessageChunk` so the client can display it. This matches the spec and gives clients actionable error information.

## Consequences

### Positive

- Multi-turn conversations will work correctly across `prompt()` calls within the same session.
- `load_session()` and `resume_session()` will restore conversation history (via Claude's server-side session, not local state).
- Cancel will be non-destructive -- sessions survive cancellation and accept future prompts.
- Rich ACP clients will receive tool kind, content, rawInput, and accumulated content on every tool update.
- TodoWrite will appear as structured plans in Zed's plan panel.
- Bug fixes eliminate resource leaks (missing await), stale state (uncleaned dicts), and silent failures (no-op `on_connect`).

### Negative

- `_SessionState` grows from 8 fields to 12 fields (adding `claude_session_id`, `cancel_event`, `tool_call_contents`, `todo_write_tool_call_ids`). Increased per-session memory, but minimal (~hundreds of bytes per session).
- Per-session SDK client management adds complexity to session lifecycle methods. Client creation/destruction must be tracked carefully to avoid subprocess leaks.
- The `resume` parameter depends on Claude's server-side session storage. If Claude's backend evicts the session (e.g., after inactivity), `resume` will fail silently or error. We must handle this gracefully (fall back to fresh session).
- Content accumulation means `ToolCallProgress` payloads grow over the tool lifecycle. For tools with large outputs, this could become expensive. Consider capping accumulated content size.

### Migration

- All existing `SubagentClient` callers continue to work unchanged. New fields (`kind`, `content`, `rawInput`) are additive on ACP schema types that already support them.
- Test recorders (`SDKClientRecorder`, `ConnRecorder`) must be updated to support `interrupt()` as `async`, `resume` in options, and per-session client resolution. No mocks required -- DI handles this.
- The `_cancelled` boolean is removed from the bridge class. Any external code checking `bridge._cancelled` (unlikely, but possible in tests) must switch to per-session `cancel_event`.
- This ADR sets the pattern for the remaining five protocol cases. The per-session state model, content accumulation, and kind mapping should be extracted into shared utilities after this first implementation validates the approach.

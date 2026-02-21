---
tags:
  - "#exec"
  - "#claude-acp-bidirectional"
date: "2026-02-21"
related:
  - "[[2026-02-21-claude-acp-bidirectional-impl-plan]]"
---

# `claude-acp-bidirectional` Phases 1-6

Implementation of all 6 ADR decisions for multi-turn bidirectional ACP communication.

- Modified: `src/vaultspec/protocol/acp/claude_bridge.py`
- Modified: `src/vaultspec/protocol/acp/client.py`
- Modified: `src/vaultspec/protocol/a2a/executors/claude_executor.py`

## Description

### Phase 1: P0 Bug Fixes (ADR Decision 6)
- **Step 1**: Fixed `on_connect()` no-op in `client.py` — now stores `conn` in `self._conn`
- **Step 2**: Fixed exception masking — differentiated `MessageParseError` from other errors, emit error text as `AgentMessageChunk`, return `"end_turn"` not `"refusal"`
- **Step 3**: Fixed `ResultMessage.is_error` stop reason — emits error text, returns `"end_turn"`
- **Step 4**: Clear `_pending_tools` and `_block_index_to_tool` at start of each `prompt()`
- **Step 5**: Fixed CLAUDECODE env var mutation in A2A executor — uses `options.env` copy instead of mutating `os.environ`

### Phase 2: Per-Session State (ADR Decision 2)
- Extended `_SessionState` with 4 new fields: `claude_session_id`, `cancel_event`, `tool_call_contents`, `todo_write_tool_call_ids`
- All session methods (`new_session`, `load_session`, `resume_session`, `fork_session`) now store SDK client in per-session state
- `prompt()` resolves SDK client from session state (falls back to bridge-level)

### Phase 3: Session Resume (ADR Decision 1)
- Extract `session_id` from SDK messages in streaming loop via `getattr(message, "session_id", None)`
- Store in `state.claude_session_id`
- `load_session()` and `resume_session()` pass `options.resume = state.claude_session_id`

### Phase 4: Abort/Cancel (ADR Decision 5)
- Per-session `asyncio.Event` for cancellation (bridge-level `_cancelled` kept for compat)
- `cancel()` uses `await sdk_client.interrupt()` (fixed missing await)
- `cancel()` no longer calls `disconnect()` — session stays alive

### Phase 5: Tool Content & Kind Mapping (ADR Decision 3)
- Added `_map_tool_kind()` — maps tool names to ACP kinds via substring matching
- Added `_get_tool_call_content()` — generates diff blocks for Edit/MultiEdit tools
- `_emit_assistant()` emits enriched `ToolCallStart` with `kind`, `content`, `raw_input`
- `_emit_user_message()` accumulates content per tool call ID

### Phase 6: TodoWrite-to-Plan (ADR Decision 4)
- Intercept TodoWrite in both `_emit_assistant()` and `_emit_stream_event()`
- Emit `AgentPlanUpdate` with mapped todo entries
- Suppress TodoWrite from `ToolCallStart` and `ToolCallProgress` events
- Track IDs in `state.todo_write_tool_call_ids`

## Tests

Syntax validation passed for all 3 modified files. Test suite updated in Phase 7.

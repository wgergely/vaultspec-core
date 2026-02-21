---
tags: ["#exec", "#claude-acp-bidirectional"]
related: ["[[2026-02-21-claude-acp-bidirectional-impl-plan.md]]"]
date: 2026-02-21
---

# Step Record: Phase 5 & 6 - Tool Content & TodoWrite

## Description

Implemented Phases 5 (Tool Content & Kind Mapping) and 6 (TodoWrite-to-Plan Conversion) of the implementation plan. Verified that Phases 1-4 (Bug Fixes, Per-Session State, Resume, Cancel) were already present in the codebase.

## Changes

### `src/vaultspec/protocol/acp/claude_bridge.py`

1.  **Added `AgentPlanUpdate` Import**: To support plan emission.
2.  **Updated `_emit_assistant`**:
    *   Intercepts `TodoWrite` tool calls, converts `todos` input to `AgentPlanUpdate`, and suppresses `ToolCallStart`.
    *   For other tools: calculates `kind` using `_map_tool_kind` and `content` using `_get_tool_call_content`.
    *   Caches tool content in `state.tool_call_contents`.
    *   Emits enriched `ToolCallStart` with `kind`, `content`, and `raw_input`.
3.  **Updated `_emit_stream_event`**:
    *   Checks `content_block_start` for `TodoWrite` tool use.
    *   Emits partial `AgentPlanUpdate` if `todos` are present in the input.
4.  **Updated `_emit_user_message`**:
    *   Suppresses `ToolCallProgress` for `TodoWrite` calls (using `state.todo_write_tool_call_ids`).
    *   Accumulates tool result text into `state.tool_call_contents`.
    *   Emits enriched `ToolCallProgress` with accumulated `content` and `raw_output`.

## Verification

*   The code now fully implements the ADR decisions regarding rich tool call metadata and plan updates.
*   The `TodoWrite` logic matches the reference implementation (interception at assistant/stream, suppression at user message).
*   Tool content accumulation allows for diff views and rich rendering in ACP clients.

## Remaining Work

*   Phase 7 (Tests) still needs to be verified/implemented if not present.

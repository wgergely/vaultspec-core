---
tags:
  - "#exec"
  - "#claude-acp-reliability"
date: "2026-02-21"
related:
  - "[[2026-02-21-acp-claude-reliability-plan.md]]"
---
# Step Record: ACP Claude Reliability & Permissions

## Description

Implemented key reliability features for the Claude ACP bridge:
1.  **Dynamic Permission Modes:** The agent can now switch between `bypassPermissions`, `acceptEdits`, and `default` modes on the fly if the prompt contains magic strings (e.g. `[ACP:PERMISSION:ACCEPT_EDITS]`). This required implementing client recreation logic in `prompt()`.
2.  **Session Recovery:** `load_session()` now gracefully recovers from bridge restarts by creating a new session state if the requested ID is unknown, rather than failing.
3.  **Tool Error Visibility:** The bridge now explicitly handles `tool_use_error` events from the SDK/CLI and reports them as `failed` tool calls to the client, ensuring errors aren't swallowed.

## Changes

### `src/vaultspec/protocol/acp/claude_bridge.py`

*   **`_SessionState`**: Added `permission_mode` field.
*   **`_build_options`**: Added `permission_mode` argument.
*   **`load_session`**: Added recovery logic (create new state if missing) and passed permission mode.
*   **`prompt`**: Added magic string scanning logic. If mode changes, the SDK client is disconnected and recreated with new options.
*   **`_emit_stream_event`**: Added handler for `tool_use_error` event type.

### `src/vaultspec/protocol/acp/tests/test_bridge_reliability.py`

*   Added new test file covering:
    *   `TestPermissionModes`: Verifies client recreation and option updates.
    *   `TestSessionRecovery`: Verifies successful load of unknown session ID.
    *   `TestToolErrors`: Verifies `tool_use_error` event mapping to `ToolCallProgress`.

## Verification

*   Run `pytest src/vaultspec/protocol/acp/tests/test_bridge_reliability.py` -> Passed (3 tests).
*   Verified that Pydantic models are correctly constructed for error reporting.

## Notes

*   Client recreation is expensive but necessary for permission mode changes as the SDK consumes options at connection time.
*   Session recovery assumes default configuration for the recovered session; this is acceptable as the Client usually re-sends context or relies on `resume` behavior (which we also wired up).

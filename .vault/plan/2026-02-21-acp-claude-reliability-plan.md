---
tags:
  - "#plan"
  - "#acp-claude-reliability"
date: "2026-02-21"
related:
  - "[[2026-02-21-acp-claude-reliability-adr]]"
  - "[[2026-02-21-acp-claude-final-audit-research]]"
---
# Implementation Plan: ACP Claude Reliability & Permissions

Enhance the Claude ACP bridge with dynamic permission modes, session recovery, and explicit tool error handling.

## 1. Verification

*   **Task:** Verify `ClaudeSDKClient` attribute mutability. Can we change `client._options.permission_mode` on the fly? Or must we reconnect?
*   **Task:** Verify `tool_use_error` event structure in `claude_agent_sdk`.

## 2. Implementation

### 2.1. Permission Modes
*   **File:** `src/vaultspec/protocol/acp/claude_bridge.py`
*   **Struct:** `_SessionState` - Add `permission_mode: str`.
*   **Method:** `prompt`
    *   Scan `prompt_text` for:
        *   `[ACP:PERMISSION:ACCEPT_EDITS]`
        *   `[ACP:PERMISSION:BYPASS]`
        *   `[ACP:PERMISSION:DEFAULT]`
    *   If found and different from `state.permission_mode`:
        *   Update `state.permission_mode`.
        *   Re-create SDK client with new options (using `disconnect` + `_build_options` + `connect`). This is safer than mutation.

### 2.2. Session Recovery
*   **Method:** `load_session`
*   **Logic:** If `session_id` not in `_sessions`:
    *   Log "Session not found, creating new session to recover".
    *   Create new `_SessionState` (defaulting `cwd`, `model` from args or bridge defaults).
    *   Proceed with connection logic.

### 2.3. Tool Error Handling
*   **Method:** `_emit_stream_event`
*   **Logic:** Add `elif event_type == "tool_use_error":`
    *   Extract error message.
    *   Emit `ToolCallProgress` with `status="failed"` and `raw_output={"error": ...}`.

## 3. Testing

*   **File:** `src/vaultspec/protocol/acp/tests/test_bridge_resilience.py` (or `test_bridge_prompt.py`)
*   **Tests:**
    *   `test_prompt_switches_permission_mode`: Send magic string, verify client recreation/option change.
    *   `test_load_session_recovers_unknown_id`: Call `load_session` with random ID, ensure success.
    *   `test_tool_use_error_event`: Feed `tool_use_error` event, verify failed status update.

## Execution Order

1.  **Phase 1** (Verification)
2.  **Phase 2** (Implementation) & **Phase 3** (Testing)

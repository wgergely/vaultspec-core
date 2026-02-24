---
tags:
  - "#exec"
  - "#claude-acp-reliability"
date: "2026-02-21"
related:
  - "[[2026-02-21-acp-claude-reliability-plan.md]]"
---
# Code Review: ACP Claude Reliability & Permissions

## 1. Summary

**Status:** **Pass**

The changes successfully implement dynamic permission modes, session recovery, and explicit tool error handling. The implementation is robust and aligns with the plan.

## 2. Findings

### 2.1. Safety & Resource Management
*   **Client Recreation:** The logic in `prompt()` calls `state.sdk_client.disconnect()` before creating a new one. This is critical for preventing subprocess leaks. Exception handling around disconnect is present.
*   **Session Recovery:** Creating a new session state on `load_session` failure is safe and improves UX.

### 2.2. Correctness
*   **Permission Switching:** The code correctly updates `state.permission_mode` and passes it to `_build_options`.
*   **Tool Errors:** The Pydantic model construction for `ToolCallProgress` was fixed during implementation (adding nested `content` structure) and now passes tests.
*   **Magic Strings:** The implementation scans the full text content of the payload, which is the correct approach.

### 2.3. Quality & Tests
*   `test_bridge_reliability.py` covers the three new features effectively.
*   Code style is consistent.

## 3. Recommendations

*   **Observation:** The magic string check iterates over all blocks. For very large prompts (images), `full_text` construction might be slightly inefficient, but given typical usage, it's negligible.
*   **Future:** If `UsageUpdate` becomes available in the SDK, it should be added to `_emit_updates`.

## 4. Conclusion

The changes are safe to merge.

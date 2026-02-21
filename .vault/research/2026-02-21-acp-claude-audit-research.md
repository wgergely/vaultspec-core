---
tags: ["#research", "#acp-claude-audit"]
related: []
date: 2026-02-21
---

# ACP Claude Implementation Audit

## 1. Executive Summary

A comprehensive audit of the local `acp claude` implementation in `src/vaultspec` against reference implementations in `tmp-ref/acp-claude-code` and `tmp-ref/acp-python-sdk` reveals critical functional gaps. The most significant issues are the lack of "Plan" synchronization (via `TodoWrite` tool handling) and incomplete session resumption logic. These gaps prevent the agent's internal planning state from being visible to the ACP client and limit the ability to maintain conversation context across sessions.

## 2. Methodology

*   **Target Codebase:** `src/vaultspec/protocol/acp` (specifically `claude_bridge.py` and `client.py`).
*   **Reference Codebase:** `tmp-ref/acp-claude-code/src/agent.ts` (TypeScript reference) and `tmp-ref/acp-python-sdk`.
*   **Focus Areas:** Protocol compliance, tool handling, session management, and permission logic.

## 3. Findings & Discrepancies

### 3.1. Missing Plan Synchronization (`TodoWrite`)

*   **Reference Behavior (`agent.ts`):** The TypeScript agent explicitly intercepts `TodoWrite` tool calls. It converts the `todos` payload into an ACP `session/update` notification with `sessionUpdate: "plan"`. This allows the UI to display the agent's checklist/plan. It also suppresses the raw tool call from the stream for this specific tool.
*   **Local Implementation (`claude_bridge.py`):** The Python bridge has **no logic** to handle `TodoWrite`. It treats it as a generic tool call.
*   **Impact:** The user never sees the agent's plan or updates to it. The "Plan" feature in ACP clients (like Zed) will remain empty.

### 3.2. Session Resumption

*   **Reference Behavior (`agent.ts`):** The TypeScript agent captures the `claudeSessionId` from the first message of a session. On resumption, it passes `resume: session.claudeSessionId` in the options to the `query` function.
*   **Local Implementation (`claude_bridge.py`):** The Python bridge *does* capture `claude_session_id` from SDK messages. However, it **does not use it** when rebuilding the session in `load_session` or `resume_session`. A comment explicitly claims: "The Claude SDK does not support true session resumption... This restores configuration only."
*   **Impact:** Restarting a session loses all conversation history, degrading the user experience significantly compared to the reference.

### 3.3. Permission Logic ("YOLO Mode")

*   **Reference Behavior:** The ACP spec defines `AllowedOutcome` with `optionId`.
*   **Local Implementation (`client.py`):** The `SubagentClient.request_permission` method implements a "YOLO mode" that blindly auto-approves using a hardcoded `"allow"` ID or the first available "allow" option.
*   **Impact:** While useful for headless operation, this bypasses the intended security model of ACP where a user (or policy) should explicitly grant permissions.

### 3.4. Tool Kind Mapping

*   **Reference Behavior:** `agent.ts` has a `mapToolKind` function.
*   **Local Implementation:** `claude_bridge.py` has a similar `_map_tool_kind` function, but it is a simplified version.
*   **Impact:** Minor, but could lead to inconsistent UI icons/grouping for tools if not aligned.

## 4. Recommendations

1.  **Implement `TodoWrite` Handling:**
    *   Modify `ClaudeACPBridge._emit_assistant` and `_emit_stream_event` (or where appropriate) to detect `TodoWrite` tool calls.
    *   Extract the `todos` list.
    *   Emit an `AgentPlanUpdate` (mapped to `sessionUpdate: "plan"`).
    *   Suppress the raw `tool_call` notification for `TodoWrite` to avoid showing it as a generic tool execution.

2.  **Enable Session Resumption:**
    *   Verify if `ClaudeAgentOptions` or `ClaudeSDKClient` in the Python SDK supports a `resume` parameter (similar to the TS `query` options).
    *   If supported, pass the stored `state.claude_session_id` when reconnecting in `load_session` and `resume_session`.

3.  **Refine Permission Logic:**
    *   Update `SubagentClient.request_permission` to support a real interactive mode or at least a more robust policy-based approval (e.g., checking env vars for "YOLO" vs "ASK").

4.  **Align Protocol Version:**
    *   Ensure `src/vaultspec` uses the same protocol version and schema definitions as the reference to avoid serialization issues.

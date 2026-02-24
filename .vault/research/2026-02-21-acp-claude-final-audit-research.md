---
tags:
  - "#research"
  - "#acp-claude-audit"
date: "2026-02-21"
related:
  - "[[2026-02-21-acp-claude-audit-research.md]]"
---
# ACP Claude Final Audit Findings

## 1. Permission Mode Magic Strings

**Finding:**
The reference implementation `agent.ts` supports changing the permission mode dynamically by checking the prompt text for specific magic strings:
*   `[ACP:PERMISSION:ACCEPT_EDITS]` -> `acceptEdits`
*   `[ACP:PERMISSION:BYPASS]` -> `bypassPermissions`
*   `[ACP:PERMISSION:DEFAULT]` -> `default`

Our `claude_bridge.py` hardcodes `bypassPermissions` in `_build_options`.

**Impact:**
Users (or Client UIs) attempting to toggle safety modes via prompt commands will be ignored. The agent will always run in YOLO mode (bypass).

## 2. Usage Updates (Tokens/Cost)

**Finding:**
Neither implementation emits `UsageUpdate` events. This is likely due to the SDK or CLI not exposing this data easily in the stream. No action needed for parity, but a potential future enhancement.

## 3. Session Loading Robustness

**Finding:**
Reference `loadSession` logic:
```typescript
    const existingSession = this.sessions.get(params.sessionId);
    if (existingSession) { return; }
    // If not found, create a new entry to allow Zed to resume conversation with a potentially restarted agent
    this.sessions.set(params.sessionId, { ... });
```
Our `load_session` logic:
```python
        state = self._sessions.get(session_id)
        if state is None:
            return None  # We return None (failure?)
```
If the bridge restarts but the Client (Zed) still has the session ID, our bridge rejects the load request. The reference *recreates* the session structure (empty state) to allow the conversation to proceed (potentially without history, or relying on `resume` later if the ID is known).

Wait, our `load_session` returns `None` which usually means "error/not found" in ACP? The spec says `loadSession` returns `LoadSessionResponse` or `null` (if void).
If we return `None` (Python), it might serialize to `null` which is success? No, `InitializeResponse` etc return objects. `load_session` returns `LoadSessionResponse | None`.
If we return `None`, the ACP library might send an error or empty response.
If the Client thinks session exists, but Bridge doesn't, we should probably allow "re-creation" or at least a graceful fallback.

However, `load_session` implies *loading persisted state*. Since we don't persist to disk, we can't really "load" a session from a previous process run.
The reference just creates a *new empty* session map entry so that `prompt` doesn't crash on "Session not found".

**Recommendation:** Update `load_session` to create a new session state if one doesn't exist, using the provided `session_id`.

## 4. Tool Error Handling

**Finding:**
Reference handles `tool_use_error` message type.
Our `_emit_updates` does *not* explicitly check for `tool_use_error`. We handle `UserMessage` with `ToolResultBlock.is_error`.
Does the Python SDK emit a specific `ToolUseError` message or event?
The Python SDK types (`claude_agent_sdk.types`) should be checked. If there is a `ToolUseError` type, we might be missing it.
However, `UserMessage` is the standard way tool results (including errors) are fed back.
If `tool_use_error` is a distinct event in the *stream* (before UserMessage), we might miss it.
Reference `agent.ts`:
```typescript
      case "tool_use_error":
        await this.client.sessionUpdate({ ..., status: "failed", ... });
```
This suggests it's an event.
Our `_emit_stream_event` handles `content_block_delta`. It does not check for a top-level event type of `tool_use_error`.
Wait, `StreamEvent` wraps the raw event.
We should check if `event.type == "tool_use_error"` or similar exists in the Python SDK `StreamEvent`.

## 5. Action Plan

1.  **Implement Permission Magic Strings:** Parse prompt for strings and update `options.permission_mode`.
2.  **Robust Session Loading:** Allow `load_session` to create a new session if missing (recover from bridge restart).
3.  **Audit Tool Errors:** Check if `tool_use_error` is a possible event type in `StreamEvent` and handle it.

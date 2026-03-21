---
tags:
  - "#adr"
  - "#acp-claude-reliability"
date: "2026-02-21"
related:
  - "[[2026-02-21-claude-sdk-verification-research]]"
  - "[[2026-02-21-acp-claude-final-audit-research]]"
---
# ACP Claude Permission & Reliability Fixes | (**status:** `superseded`)

**SUPERSEDED** — This ADR is fully superseded by
`[[2026-02-24-subagent-protocol-adr]]` (Unified A2A Protocol Stack — Full
Rewrite). ACP bridges are being deleted, not hardened. Do not implement any
decisions from this document.

## Context

The final audit of `claude_bridge.py` vs `acp-claude-code` revealed gaps in:

1. **Permission Control:** The reference supports dynamic permission switching via prompt magic strings (e.g. `[ACP:PERMISSION:ACCEPT_EDITS]`). The bridge hardcodes `bypassPermissions`.
2. **Session Robustness:** The reference creates a new session if `loadSession` is called for an unknown ID (handling bridge restarts). The bridge fails.
3. **Error Handling:** The reference handles `tool_use_error` stream events. The bridge might miss these.

## Decision

We will implement the following changes to achieve full parity and reliability:

1. **Dynamic Permission Modes:**
    * Modify `_SessionState` to store `permission_mode` (default: `bypassPermissions` or read from env).
    * In `prompt()`, scan the prompt text for:
        * `[ACP:PERMISSION:ACCEPT_EDITS]` -> `acceptEdits`
        * `[ACP:PERMISSION:BYPASS]` -> `bypassPermissions`
        * `[ACP:PERMISSION:DEFAULT]` -> `default`
    * If the mode changes, update `_SessionState` and recreate/update the SDK client options for the *next* turn (or restart current if needed? Reference just sets it on `query` options).
    * *Correction:* The Python SDK `ClaudeAgentOptions` is passed at creation. `query()` doesn't seem to take options override. We might need to check if we can update `sdk_client._options` or if we need to reconnect. Given `prompt()` is where we receive the text, and `query()` is called immediately, if we need to change permissions for *that* query, we might need to update the options on the *existing* client if possible, or assume the SDK supports dynamic updates.
    * *Strategy:* Update `sdk_client._options.permission_mode` if accessible, or accept that it applies to the *next* session creation (which isn't ideal). Wait, the reference passes `options` to `query`. The Python SDK `query` signature is `(prompt)`. It uses the options from `__init__`.
    * *Revised Strategy:* If permission mode changes, we must `disconnect` and `connect` (recreate client) with new options *before* sending the query. Or, if `sdk_client` allows property mutation, do that. We will try recreation to be safe, reusing `load_session` logic effectively.

2. **Session Recovery in `load_session`:**
    * If `session_id` is not in `self._sessions`, do NOT return `None`.
    * Instead, create a new `_SessionState` with default config (or derived from args if provided) and initialize a new SDK client.
    * This ensures `load_session` always results in a usable session.

3. **Tool Use Error Handling:**
    * In `_emit_stream_event`, add a branch for `event_type == "tool_use_error"`.
    * Emit `ToolCallProgress(status="failed", raw_output={"error": ...})`.

## Consequences

**Positive:**

* Power users can control permissions.
* Client reconnects (after bridge restart) work seamlessly.
* Tool errors are reported explicitly.

**Negative:**

* Recreating client on permission change adds latency.

## Compliance

* **Tags**: `#adr`, `#acp-claude-reliability`
* **Related**: `[[2026-02-21-acp-claude-final-audit-research]]`

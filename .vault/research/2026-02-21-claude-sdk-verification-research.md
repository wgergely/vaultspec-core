---
tags:
  - "#research"
  - "#acp-claude-reliability"
date: "2026-02-21"
related:
  - "[[2026-02-21-acp-claude-reliability-plan.md]]"
---
# Claude SDK Verification Findings

## 1. Options Mutability

`ClaudeAgentOptions` is a dataclass. This means its fields are mutable *on the options object itself*. However, the `ClaudeSDKClient` likely consumes these options at connection time (to spawn the process).

If `permission_mode` is passed as a flag to the subprocess, changing it on the options object *after* connection won't affect the running process. We **must** reconnect (destroy and recreate client) to apply new permission modes. This validates the "recreate client" strategy in the plan.

## 2. Event Types

`StreamEvent` is available. The raw event dictionary is inside `event`.
The `acp-claude-code` reference uses `tool_use_error`. We can assume the Python SDK emits this same event type if it wraps the same CLI.

## 3. Conclusion

Proceed with the plan:
*   Recreate client on permission change.
*   Handle `tool_use_error` event.

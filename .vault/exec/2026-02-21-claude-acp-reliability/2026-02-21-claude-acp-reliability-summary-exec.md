---
tags:
  - '#exec'
  - '#claude-acp-reliability'
date: '2026-02-21'
related:
  - '[[2026-02-21-acp-claude-reliability-plan]]'
---

# Phase Summary: ACP Claude Reliability & Permissions

## Overview

Completed the final phase of auditing and upgrading the `acp claude` implementation. This phase focused on parity with the reference implementation regarding permission handling, session robustness, and error reporting.

## Completed Work

1. **Dynamic Permission Modes:**
   - Implemented detection of `[ACP:PERMISSION:...]` magic strings in prompts.
   - Added logic to disconnect and recreate the SDK client with the new permission mode on the fly.
   - Updated `_SessionState` to track permission modes.
1. **Session Recovery:**
   - Updated `load_session` to automatically create a new session if the requested ID is not found. This allows clients to transparently recover connection to a restarted bridge.
1. **Tool Error Handling:**
   - Added specific handling for `tool_use_error` events in the stream.
   - These are now emitted as `ToolCallProgress` with `status="failed"`, ensuring errors are visible to the user.
1. **Testing:**
   - Added `src/vaultspec/protocol/acp/tests/test_bridge_reliability.py` with 3 passing tests.

## Outcome

The Claude ACP bridge now supports:

- Full multi-modal inputs (Images, Resources).
- Bidirectional features (Plans, Tool Content).
- Reliable session management (Resume, Recovery).
- Power-user permission controls.

The implementation is now fully compliant with the ACP protocol and matches the capabilities of the reference `acp-claude-code` bridge.

## Next Steps

- None. All identified gaps have been closed.

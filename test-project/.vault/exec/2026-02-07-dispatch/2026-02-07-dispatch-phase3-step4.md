---
feature: dispatch
phase: phase3
step: 4
date: 2026-02-07
status: complete
related:
  - "[[2026-02-07-dispatch-phase3-plan]]"
---

# Step 4: Implement File-Watching for list_changed Notifications

## Summary

Added mtime-based file change detection and background polling to `mcp_dispatch.py`. When `.rules/agents/*.md` files are added, removed, or modified, the agent resource cache is invalidated and re-built. A background polling coroutine runs every 5 seconds and emits `resources/list_changed` MCP notifications when changes are detected.

## Implementation

### Change Detection

- `_snapshot_mtimes()` -- returns `name -> mtime_ns` dict for all agent files
- `_has_changes()` -- compares current mtimes to cached `_agent_mtimes`, returns True if files added/removed/modified
- `_agent_mtimes: dict[str, float]` -- stored alongside `_agent_cache`, updated on every registration

### Cache Refresh

- `_refresh_if_changed() -> bool` -- orchestrates check + rebuild, returns True if refreshed
- `_register_agent_resources()` now clears stale `agents://` entries from `_resource_manager._resources` before adding current ones, enabling re-registration on file changes

### Background Polling

- `_poll_agent_files()` -- async coroutine that runs every `_POLL_INTERVAL` (5s) and calls `_refresh_if_changed()` + `_send_list_changed()`
- `_send_list_changed()` -- best-effort notification via `request_context.session.send_resource_list_changed()`; silently skips if no active session (background task has no request context; notification will fire if a concurrent request is being handled)
- Polling task injected via overriding `mcp.run_stdio_async` in `main()`, properly cancelled on server shutdown

### Design Decisions

- **Mtime polling over watchdog:** avoids external dependency; acceptable for Phase 3 per plan guidance
- **Best-effort notifications:** `list_changed` cannot be sent from a background task without an active session; this is a known limitation of the stdio transport where the session is only accessible during request handling. The cache refresh still happens, so the next `resources/list` call will reflect changes even without the notification.

## Verification

- Module loads with 9 agents cached, mtimes tracked
- `_has_changes()` returns False when files unchanged
- `_refresh_if_changed()` returns False when no changes
- All 82 existing tests pass (31 dispatch + 51 task engine)

## Files Modified

- `.rules/scripts/mcp_dispatch.py` -- added mtime tracking, change detection, polling, notification

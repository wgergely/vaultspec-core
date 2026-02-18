---
tags:
  - "#exec"
  - "#uncategorized"
date: 2026-02-07
---
# Step 4: Implement dispatch_agent Tool (Synchronous)

## Changes

### acp_dispatch.py (refactored)

- Added exception classes: `AgentNotFoundError`, `TaskFileNotFoundError`, `DispatchError`
- `load_agent()`: raises `AgentNotFoundError` instead of `sys.exit(1)`
- `parse_task_file()`: raises `TaskFileNotFoundError` instead of `sys.exit(1)`
- `run_dispatch()`: returns `str` (response text) instead of `None`; raises `DispatchError` on failure
- CLI `main()` unchanged (catches exceptions at CLI boundary)

### mcp_dispatch.py (implemented)

- `dispatch_agent` tool:
  - Validates `mode` parameter
  - Resolves task file paths relative to project root
  - Calls `run_dispatch()` directly (async-to-async, no event loop nesting)
  - Returns structured JSON with status, agent, model, duration, summary, response
  - Catches `AgentNotFoundError`, `DispatchError`, and generic exceptions

## Verification

- Server loads correctly with both tools registered
- Missing agent returns `{"status": "failed", "error": "Agent 'x' not found..."}`
- Invalid mode returns `{"status": "failed", "error": "Invalid mode..."}`
- Successful dispatch returns `{"status": "completed", "response": "..."}` (untested with live agent)

## Design Decisions

- `run_dispatch()` is already async, so it integrates directly with FastMCP's async event loop
- Response text is captured via `client.response_text` in the ACP client
- File path resolution uses `ROOT_DIR / task` for relative paths
- Duration tracking via `time.monotonic()` for reliable elapsed time

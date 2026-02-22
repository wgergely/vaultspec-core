---
tags:
  - "#exec"
  - "#protocol-stack"
date: "2026-02-22"
related:
  - "[[2026-02-22-protocol-stack-deep-audit-plan]]"
---

# `protocol-stack` Track A `Steps 1b-1c`

Surfaced session_id in MCP and added resume_session_id to dispatch_agent.

- Modified: `src/vaultspec/orchestration/task_engine.py`
- Modified: `src/vaultspec/subagent_server/server.py`

## Description

**Step 1b:** Added `get_session_id(task_id)` method to `TaskEngine` (paired
with existing `set_session_id`). Updated `get_task_status()` to include
`session_id` in the response JSON when available.

**Step 1c:** Added `resume_session_id: str | None = None` to
`dispatch_agent()` signature. Passed through to `_run_subagent_fn()`.

## Tests

MCP callers can now retrieve session IDs via `get_task_status` and pass
them back via `dispatch_agent` for session resume.

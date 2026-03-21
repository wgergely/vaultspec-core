---
tags:
  - '#exec'
  - '#protocol-stack'
date: '2026-02-22'
related:
  - '[[2026-02-22-protocol-stack-deep-audit-plan]]'
---

# `protocol-stack` Track A `Step 1a`

Fixed root cause: `run_subagent()` now calls `conn.resume_session()` when
`resume_session_id` is set.

- Modified: `src/vaultspec/orchestration/subagent.py`

## Description

At line 370, replaced the unconditional `conn.new_session()` call with a
conditional branch. When `resume_session_id` is provided, calls
`conn.resume_session(cwd, session_id, mcp_servers)` instead. Both Claude
and Gemini bridges already implement `resume_session()` with matching
signatures. A lightweight `_Session` object wraps the session_id for the
resumed case.

## Tests

Protocol isolation tests (`test_subagent_gemini.py`, `test_subagent_claude.py`)
already pass `resume_session_id` — they will now exercise the real resume
path instead of creating independent sessions.

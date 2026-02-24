---
tags:
  - "#exec"
  - "#protocol-stack"
date: "2026-02-22"
related:
  - "[[2026-02-22-protocol-stack-deep-audit-plan]]"
  - "[[2026-02-22-protocol-stack-deep-audit-adr]]"
  - "[[2026-02-22-protocol-stack-deep-audit-research]]"
---
# `protocol-stack` deep audit execution summary

Executed all 4 authorized decision tracks from
[[2026-02-22-protocol-stack-deep-audit-adr]].

## Modified Files

- `src/vaultspec/orchestration/subagent.py` — session resume branch (1a)
- `src/vaultspec/orchestration/task_engine.py` — `get_session_id()` (1b)
- `src/vaultspec/subagent_server/server.py` — session_id in status, resume param (1b, 1c)
- `src/vaultspec/subagent_cli.py` — 6 CLI flags, debug on serve subparsers (2a, 2c)
- `src/vaultspec/cli.py` — fixed stale MODULE_PATHS (2b)
- `src/vaultspec/team_cli.py` — spawn command (2d)
- `src/vaultspec/protocol/a2a/executors/gemini_executor.py` — session reuse (1e)
- `src/vaultspec/mcp_tools/team_tools.py` — async pattern, get_team_task_status, relay_output (3b, 3c)
- `src/vaultspec/orchestration/utils.py` — start_dir param on find_project_root (4b)
- `src/vaultspec/orchestration/tests/test_utils.py` — removed monkeypatch.chdir (4b)
- `tests/protocol/isolation/test_subagent_gemini.py` — session_id assertion (1f)
- `tests/protocol/isolation/test_subagent_claude.py` — session_id assertion (1f)

## Created Files

- `src/vaultspec/orchestration/team_task_engine.py` — TeamTaskEngine (3a)
- `src/vaultspec/tests/__init__.py` — package marker (4a)

## Description

**Track A (Session Management):** Fixed the systemic root cause where
`run_subagent()` always called `conn.new_session()`. Now branches on
`resume_session_id` to call `conn.resume_session()`. Propagated through
MCP (`dispatch_agent` param + `get_task_status` response), CLI
(`--resume-session` flag), and Gemini A2A executor (session reuse on
subsequent turns). Multi-turn tests now assert session identity.

**Track B (Team Async):** Introduced `TeamTaskEngine` mirroring the
subagent `TaskEngine` pattern. Refactored `dispatch_task`,
`broadcast_message`, and `send_message` to return immediately with a
taskId. Added `get_team_task_status` and `relay_output` MCP tools (10 team
tools total, up from 8).

**Track C (CLI/MCP Parity):** Added 6 missing CLI flags (`--max-turns`,
`--budget`, `--effort`, `--output-format`, `--resume-session`,
`--mcp-servers`). Fixed stale `MODULE_PATHS` from pre-restructure paths.
Registered `--debug`/`--verbose` on `serve` and `a2a-serve` subparsers.
Added `spawn` command to team CLI.

**Track D (Test Fixes):** Created missing `__init__.py`. Refactored
`find_project_root()` to accept `start_dir`, eliminating banned
`monkeypatch.chdir`. Clarified `monkeypatch.setenv` policy in MEMORY.md.
Step 4c (stale constants removal) deferred per user decision.

## Tests

Protocol isolation tests (`tests/protocol/isolation/`) validate the full
session resume chain (Track A). Run with:
```bash
python -m pytest tests/protocol/isolation/ -x --tb=short
```

Full suite verification:
```bash
python -m pytest src/vaultspec/ tests/ -x --tb=short
```

Note: Protocol isolation tests require live API keys for Gemini and Claude.

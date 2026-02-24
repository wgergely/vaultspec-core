---
tags:
  - "#exec"
  - "#claude-a2a-overhaul"
date: "2026-02-22"
related:
  - "[[2026-02-21-claude-a2a-overhaul-impl-plan]]"
  - "[[2026-02-21-claude-a2a-overhaul-adr]]"
---
# `claude-a2a-overhaul` Phase 4: Wiring

Registered team tools in the unified `vaultspec-mcp` server and wired
`set_root_dir()` into the server's `main()` initialization path.

- Modified: `src/vaultspec/server.py`
- Modified: `tests/subagent/test_mcp_protocol.py`

## Description

Added `register_team_tools(mcp)` call to `create_server()` alongside the
existing `register_subagent_tools(mcp)`. Added `set_team_root_dir(root_dir)`
to `main()` so team tools receive the workspace root from config.

Updated the unified server docstring and instructions to mention all 8 team
tools. Updated `test_all_five_tools_registered` → `test_all_tools_registered`
to assert the full set of 13 tools (5 subagent + 8 team).

## Tests

- `tests/subagent/test_mcp_protocol.py` — updated tool count assertion, passes
- Full regression: 255/256 pass (1 pre-existing E2E failure)
- Smoke test: `create_server()` imports and creates successfully

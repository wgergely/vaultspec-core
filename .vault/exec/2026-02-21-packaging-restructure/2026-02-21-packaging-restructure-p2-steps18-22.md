---
tags:
  - "#exec"
  - "#packaging-restructure"
date: "2026-02-21"
related:
  - "[[2026-02-21-packaging-restructure-p1p2-plan]]"
  - "[[2026-02-21-packaging-restructure-adr]]"
---

# Phase 2: Unified MCP Server (Steps 18-22)

## Step 18: Create `src/vaultspec/server.py`

Created the unified entry point with:
- `create_server()` factory function that instantiates `FastMCP(name="vaultspec-mcp")`
- `_lifespan()` async context manager composing tool module lifespans
- `main()` function wired to `[project.scripts] vaultspec-mcp`
- Modular pattern: calls `register_subagent_tools(mcp)` from the subagent module

## Step 19: Refactor `subagent_server/server.py`

Structural refactoring (no behavior changes):
- Removed module-level `mcp = FastMCP(...)` instance
- Added `_mcp_ref` global set by `register_tools()` for resource management
- Extracted `register_tools(mcp: FastMCP)` that programmatically registers all 5 tools
- Extracted `subagent_lifespan()` async context manager for agent-file polling
- Kept `main()` as legacy standalone entry point (creates its own FastMCP internally)
- All helper functions, tool functions, and globals remain importable from the same paths

## Step 20: Create `src/vaultspec/mcp_tools/` stubs

Created package with three stub modules:
- `vault_tools.py` -- Phase 3 vault audit/management tools
- `team_tools.py` -- Phase 4 multi-agent team tools
- `framework_tools.py` -- Phase 3 framework CLI tools

Each exposes `register_tools(mcp: FastMCP) -> None` as a no-op.

## Step 21: Replace `vs-subagent-mcp` references

Updated 8 files outside `.vault/`:
- `extension.toml` -- entry point and provides
- `src/vaultspec/orchestration/subagent.py` -- ACP client name
- `.claude/rules/vaultspec-subagents.builtin.md`
- `.agent/rules/vaultspec-subagents.builtin.md`
- `.vaultspec/rules/rules/vaultspec-subagents.builtin.md`
- `.vaultspec/docs/concepts.md`
- `.vaultspec/docs/cli-reference.md`
- `tests/subagent/test_mcp_protocol.py`

Historical `.vault/` documents preserved unchanged (12 files).

## Step 22: Verification

- `uv sync --dev` -- resolved 116 packages, no errors
- `from vaultspec.server import main` -- importable
- `from vaultspec.subagent_server.server import register_tools, subagent_lifespan` -- importable
- `from vaultspec.mcp_tools import vault_tools, team_tools, framework_tools` -- importable
- `pytest` -- **1017 passed**, 86 skipped, 75 deselected (zero regressions)
- MCP protocol tests (16 tests via `call_tool`) -- all pass
- No `vs-subagent-mcp` references remain in production code/config/rules

## Files Changed

- `src/vaultspec/server.py` (new)
- `src/vaultspec/subagent_server/server.py` (refactored)
- `src/vaultspec/mcp_tools/__init__.py` (new)
- `src/vaultspec/mcp_tools/vault_tools.py` (new)
- `src/vaultspec/mcp_tools/team_tools.py` (new)
- `src/vaultspec/mcp_tools/framework_tools.py` (new)
- `tests/subagent/test_mcp_protocol.py` (updated import)
- `tests/e2e/test_mcp_e2e.py` (updated import)
- `extension.toml` (renamed server)
- `src/vaultspec/orchestration/subagent.py` (renamed client)
- `.claude/rules/vaultspec-subagents.builtin.md` (renamed server)
- `.agent/rules/vaultspec-subagents.builtin.md` (renamed server)
- `.vaultspec/rules/rules/vaultspec-subagents.builtin.md` (renamed server)
- `.vaultspec/docs/concepts.md` (renamed server)
- `.vaultspec/docs/cli-reference.md` (renamed server)

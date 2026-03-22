---
tags:
  - '#plan'
  - '#team-mcp-integration'
date: '2026-02-21'
related:
  - '[[2026-02-20-team-mcp-integration-p1-adr]]'
  - '[[2026-02-20-team-mcp-integration-research]]'
  - '[[2026-02-20-team-mcp-surface-design-reference]]'
---

# `team-mcp-integration` Phase 1 Plan — Unified `vs-agents-mcp` Server

Create the unified `vs-agents-mcp` MCP server that merges subagent dispatch and team
orchestration tools into a single FastMCP instance, then surface the team capability
through a `vaultspec-team` skill and update all rules references. The ADR
\[[2026-02-20-team-mcp-integration-p1-adr]\] is binding.

## Proposed Changes

The integration closes three gaps identified in
\[[2026-02-20-team-mcp-integration-research]\]:

1. **Missing unified MCP server** -- `mcp.json` currently declares `vaultspec-mcp` via
   `uv run vaultspec-mcp`, but `vaultspec.server` does not exist. A new
   `src/vaultspec/agent_server/` package will house the unified FastMCP server exposing
   all 13 tools (5 subagent + 8 team). The `vaultspec-mcp` console script entry point
   in `pyproject.toml` will be rewired to `vaultspec.agent_server.server:main`.

1. **Missing `vaultspec-team` skill** -- A new skill file at
   `.vaultspec/rules/skills/vaultspec-team.md` will mirror the structure of
   `vaultspec-subagent.md` and document the MCP-based team dispatch pathway.

1. **Stale dispatch instructions** -- 13 rules files (22 locations) reference only
   `vaultspec-subagent`. Each must gain conditional language distinguishing single-agent
   from team dispatch. Both `vaultspec-subagents.builtin.md` copies must reference
   `vs-agents-mcp`.

Key design decisions from the ADR:

- `subagent_server/` is preserved intact; its tools are carried into `agent_server/`
  via import delegation (not forked).

- `team_cli.py` and `subagent_cli.py` remain standalone CLIs. No CLI merge.

- Each team tool loads/saves session from disk (idempotent across MCP requests).

- Windows `ProactorEventLoopPolicy` applied in the serve entry point.

- The existing 53-test subagent server suite is the acceptance bar; all must pass.

Source paths (actual codebase, not ADR's legacy `.vaultspec/lib/` paths):

- Subagent server: `src/vaultspec/subagent_server/server.py` (689 lines, 5 tools)
- Team orchestration: `src/vaultspec/orchestration/team.py` (561 lines, 7 public methods)
- Team CLI: `src/vaultspec/team_cli.py` (session persistence helpers already present)
- MCP config: `mcp.json` (currently `vaultspec-mcp` via `uv run`)
- Console scripts: `pyproject.toml` `[project.scripts]`

## Tasks

- `Phase 1` -- Create `agent_server/` module with unified FastMCP server

  1. Create `src/vaultspec/agent_server/__init__.py` (empty).
  1. Create `src/vaultspec/agent_server/server.py` with a `FastMCP("vs-agents-mcp", lifespan=_server_lifespan)` instance. The lifespan must mirror `subagent_server/server.py` exactly: register agent file resources, spawn background polling task, and handle graceful shutdown. Import and re-expose the 5 existing subagent tools (`list_agents`, `dispatch_agent`, `get_task_status`, `cancel_task`, `get_locks`) by delegating to the existing `subagent_server` helpers -- do NOT fork the implementations.
  1. In the same `server.py`, implement the 8 team tools (`create_team`, `get_team_status`, `list_teams`, `dispatch_task`, `collect_results`, `relay_message`, `dissolve_team_session`, `ping_team_members`) following the surface design in \[[2026-02-20-team-mcp-surface-design-reference]\]. Each tool must: parse params, load session from disk via `team_cli._load_session()` (or inline equivalent), instantiate `TeamCoordinator`, call the appropriate method, and return JSON. Use `ToolAnnotations` with `readOnlyHint=True` for read-only tools (`get_team_status`, `list_teams`, `ping_team_members`).
  1. Add a `main(root_dir=None, content_root=None)` entry point in `server.py` that initializes global state (same pattern as `subagent_server`), applies `asyncio.WindowsProactorEventLoopPolicy()` on Windows, and calls `mcp.run(transport="stdio")`.

- `Phase 2` -- Wire entry points and `mcp.json`

  1. Update `pyproject.toml` `[project.scripts]`: change `vaultspec-mcp` from `vaultspec.server:main` to `vaultspec.agent_server.server:main`. This makes `uv run vaultspec-mcp` start the unified server.
  1. Verify `mcp.json` requires no change (it already uses `uv run vaultspec-mcp`). If the args pattern differs, update to match.
  1. Add a `serve` subcommand to `team_cli.py` that delegates to `agent_server.server.main()` (same pattern as `subagent_cli.py`'s `command_serve`). This provides `vaultspec-team serve` as an alternative entry point.

- `Phase 3` -- Create `vaultspec-team` skill and update rules

  1. Create `.vaultspec/rules/skills/vaultspec-team.md` following the 72-line structural template from `vaultspec-subagent.md` (5 sections: Title/Warning, Usage, Tooling Strategy, Examples, Behavior). Document the 8 team MCP tools with usage examples. Include the same mandatory tooling block (fd, rg, sg, sd).
  1. Update `vaultspec-subagents.builtin.md` (both copies: `.claude/rules/` and `.vaultspec/rules/`) to reference `vs-agents-mcp` as the MCP server name and acknowledge `vaultspec-team` as the parallel dispatch pathway for multi-agent work.
  1. Update all 7 workflow skill files (`vaultspec-adr.md`, `vaultspec-execute.md`, `vaultspec-research.md`, `vaultspec-code-review.md`, `vaultspec-curate.md`, `vaultspec-code-reference.md`, `vaultspec-write-plan.md`) with conditional dispatch language: "Single agent: Invoke `vaultspec-subagent` / Team: Invoke `vaultspec-team`".
  1. Update the 4 agent files (`vaultspec-complex-executor.md`, `vaultspec-standard-executor.md`, `vaultspec-simple-executor.md`, `vaultspec-adr-researcher.md`) with the same conditional language. For mandatory code review blocks, add: "Team: Invoke `vaultspec-team` with role=reviewer".
  1. Update framework-level references in `CLAUDE.md` and `framework.md` (2 locations) to include `vaultspec-team` in the dispatch table.

- `Phase 4` -- Tests

  1. Create `src/vaultspec/agent_server/__init__.py` test package at `src/vaultspec/agent_server/tests/__init__.py` and `conftest.py`.
  1. Create `src/vaultspec/agent_server/tests/test_unified_server.py`. Write tests that verify: (a) all 13 tools are registered on the FastMCP instance, (b) the 5 subagent tools delegate correctly to existing implementations, (c) `create_team` / `get_team_status` / `list_teams` / `dissolve_team_session` round-trip through session persistence, (d) `dispatch_task` fan-out works with mock `EchoExecutor` ASGI apps. Use `httpx.ASGITransport` for in-process testing (same pattern as `orchestration/tests/conftest.py`).
  1. Run the existing 53-test `subagent_server` suite and confirm zero regressions. The subagent tools in `agent_server` must produce identical output.
  1. Run the full `pytest` suite to confirm no import breakages from the `pyproject.toml` entry point change.

## Parallelization

Phase 1 (server module) must complete before Phase 2 (wiring) and Phase 4 (tests).
Phase 3 (rules/skills) is fully independent of Phases 1-2 and can proceed in parallel.

Recommended two-agent split:

- Agent A: Phases 1 -> 2 -> 4 (code and tests)
- Agent B: Phase 3 (rules surface updates)

Within Phase 1, Steps 1-2 (subagent delegation) can be validated independently of
Steps 3-4 (team tools), enabling incremental testing.

## Verification

**Tool registration completeness:** The unified server must expose exactly 13 tools.
A test that introspects `mcp.list_tools()` and asserts the count and names is the
primary acceptance criterion.

**Subagent backward compatibility:** All 53 existing subagent server tests must pass
against the new `agent_server` module with zero modifications. If any test imports
`subagent_server.server` directly, it continues to work -- we are not removing the
old module.

**Team tool round-trip:** `create_team` -> `get_team_status` -> `dispatch_task` ->
`dissolve_team_session` must succeed end-to-end using in-process mock agents (no
live LLM required). Session files must appear in and disappear from
`.vault/logs/teams/`.

**Entry point validation:** `uv run vaultspec-mcp` must start the unified server
(not crash with `ModuleNotFoundError`). Verify by running with `--help` or a brief
stdio handshake.

**Rules coverage audit:** After Phase 3, grep for `vaultspec-subagent` across all
rules files. Every occurrence must be accompanied by a `vaultspec-team` alternative
(except in `vaultspec-subagent.md` itself). Any file that mentions only single-agent
dispatch is a verification failure.

**No orphaned references:** `vs-subagent-mcp` must not appear in `mcp.json` or any
rules file after completion. All references should point to `vs-agents-mcp`.

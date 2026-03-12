---
tags:
  - "#research"
  - "#agent-removal"
date: "2026-03-05"
related:
  - "[[2026-02-24-a2a-adr]]"
---

# `agent-removal` research: `obsolete-agent-management-audit`

Audit of `src/vaultspec` to identify all code, CLI commands, and MCP tools related to agent management, A2A protocol, sub-agents, and teams that are now obsolete and slated for removal.

## Findings

### CLI Commands to be Removed
- `vaultspec team`: All subcommands (create, status, list, assign, broadcast, message, spawn, dissolve).
- `vaultspec subagent`: All subcommands (run, serve, a2a-serve, list).
- `vaultspec server`: All subcommands (start, stop, list, logs) used for A2A daemon management.
- `vaultspec agents`: All subcommands (list, add, show, edit, remove, rename, sync, set-tier).

### MCP Tools to be Removed
- `src/vaultspec/mcp_server/subagent_tools.py`: Tools for subagent dispatch and management.
- `src/vaultspec/mcp_server/team_tools.py`: Tools for multi-agent team coordination.

### Library Code/Modules to be Removed
- `src/vaultspec/core/agents.py`: Core logic for agent persona management and tool translation.
- `src/vaultspec/orchestration/subagent.py`: Implementation of sub-agent dispatch and execution.
- `src/vaultspec/orchestration/team.py`: Team coordination logic.
- `src/vaultspec/orchestration/team_session.py`: Session persistence for teams.
- `src/vaultspec/orchestration/team_task_engine.py`: Background task management for teams.
- `src/vaultspec/protocol/a2a/`: The entire directory containing the Agent-to-Agent protocol implementation.
- `src/vaultspec/team_cli.py`, `src/vaultspec/subagent_cli.py`, `src/vaultspec/server_cli.py`: CLI entry point files.

### Core Entry Points requiring Updates
- `src/vaultspec/__main__.py`:
    - Remove `team`, `server`, `subagent`, and `mcp` (if it only hosts agent tools) from `NAMESPACES`.
    - Remove `agents` from `SPEC_COMMANDS`.
    - Clean up the `main()` routing logic.
- `src/vaultspec/__init__.py`: Remove docstrings and references to multi-agent teams, A2A protocols, and sub-agent dispatch.
- `src/vaultspec/spec_cli.py`: Remove the `agents` resource definition and its associated subcommands from the argument parser and dispatch logic.
- `src/vaultspec/core/enums.py`: Remove `Tool.AGENTS`, `Resource.AGENTS`, `FileName.AGENTS`, and `DirName.AGENTS`.
- `src/vaultspec/core/types.py`: Remove global path variables for `AGENTS_SRC_DIR` and remove `Tool.AGENTS` from the `TOOL_CONFIGS` dictionary.

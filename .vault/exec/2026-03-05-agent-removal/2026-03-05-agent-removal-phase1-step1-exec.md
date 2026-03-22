---
tags:
  - '#exec'
  - '#agent-removal'
date: '2026-03-05'
related:
  - '[[2026-03-05-agent-removal-plan]]'
---

# `agent-removal` `phase1` `step1`

Phase 1: Remove CLI Commands and MCP Tools. Deleted CLI entry points and MCP tools that have been migrated to the `vaultspec-a2a` repository.

- Deleted: `[[src/vaultspec/team_cli.py]]`
- Deleted: `[[src/vaultspec/subagent_cli.py]]`
- Deleted: `[[src/vaultspec/server_cli.py]]`
- Deleted: `[[src/vaultspec/mcp_server/subagent_tools.py]]`
- Deleted: `[[src/vaultspec/mcp_server/team_tools.py]]`

## Description

The following files were removed as part of the initial phase of the agent removal plan:

- CLI entry points for `team`, `subagent`, and `server` commands.
- MCP tools for subagent and team coordination.

These components are now handled by the separate `vaultspec-a2a` project, and their removal from the core repository simplifies the architecture and reduces maintenance overhead.

## Tests

Manual verification that the files are deleted.
Subsequent phases will address the removal of imports and core registration for these commands/tools.

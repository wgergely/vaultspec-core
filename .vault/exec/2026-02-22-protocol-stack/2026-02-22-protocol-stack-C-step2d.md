---
tags:
  - "#exec"
  - "#protocol-stack"
date: "2026-02-22"
related:
  - "[[2026-02-22-protocol-stack-deep-audit-plan]]"
---

# `protocol-stack` Track C `Step 2d`

Added `spawn` command to team CLI, completing MCP tool parity.

- Modified: `src/vaultspec/team_cli.py`

## Description

The team CLI already had 7 of 8 MCP tool equivalents (create, status, list,
assign, broadcast, message, dissolve). Added the missing `spawn` command
which wraps `TeamCoordinator.spawn_agent()`. The command accepts `--name`
(team), `--agent` (logical name), `--script` (Python A2A server script),
and `--port`.

After spawning, the command re-saves the team session JSON to persist the
new member.

## Tests

All 8 MCP team tool equivalents now have CLI counterparts.

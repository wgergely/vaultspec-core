---
tags:
  - '#reference'
  - '#agent-removal'
date: '2026-03-05'
related:
  - '[[2026-03-05-agent-removal-research]]'
---

# `agent-removal` reference: `internal-agent-references`

Audit of internal references to agent management and A2A code in `src/vaultspec` and `tests/`.

## Findings

### CLI Entry Points

- `src/vaultspec/__main__.py`: Subcommands `team`, `server`, `subagent`, and `agents`.
- `src/vaultspec/team_cli.py`: Entire file (Team management logic).
- `src/vaultspec/subagent_cli.py`: Entire file (Subagent dispatch logic).
- `src/vaultspec/server_cli.py`: Entire file (A2A server lifecycle).
- `src/vaultspec/spec_cli.py`: References to the `agents` command.

### Protocol Layer

- `src/vaultspec/protocol/a2a/`: Entire directory (Core A2A protocol implementation).
- `src/vaultspec/protocol/providers/base.py`: Abstract methods related to A2A process preparation (e.g., `prepare_process`).
- `src/vaultspec/protocol/providers/claude.py`: Implementation of `prepare_process` for A2A.
- `src/vaultspec/protocol/providers/gemini.py`: Implementation of `prepare_process` for A2A.

### Orchestration Layer

- `src/vaultspec/orchestration/subagent.py`: A2A-based subagent dispatching logic.
- `src/vaultspec/orchestration/team.py`: Team coordination logic.
- `src/vaultspec/orchestration/team_session.py`: Session management for multi-agent teams.
- `src/vaultspec/orchestration/team_task_engine.py`: A2A-compatible task engine.

### MCP Integration

- `src/vaultspec/mcp_server/subagent_tools.py`: MCP tools for subagent dispatch.
- `src/vaultspec/mcp_server/team_tools.py`: MCP tools for team coordination.

### Configuration

- `src/vaultspec/config/config.py`: Fields `a2a_default_port`, `a2a_host`, `agent_mode`, `agent_dir`, and related environment variable mappings (`VAULTSPEC_A2A_*`, `VAULTSPEC_AGENT_*`).

### Test Suite

- `src/vaultspec/protocol/a2a/tests/`: All files.
- `tests/protocol/cross/test_team_mixed.py`: Multi-agent team tests.
- `tests/protocol/isolation/test_team_provider.py`: Provider-specific team tests.
- `src/vaultspec/orchestration/tests/test_e2e.py`: A2A integration tests.
- `src/vaultspec/orchestration/tests/test_load_agent.py`: Agent loading tests.

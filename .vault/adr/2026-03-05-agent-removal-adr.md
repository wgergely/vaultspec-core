---
# ALLOWED TAGS - DO NOT REMOVE
# REFERENCE: #adr #audit #exec #plan #reference #research #{feature}
# Directory tag (hardcoded - DO NOT CHANGE - based on .vault/adr/ location)
# Feature tag (replace {feature} with your feature name, e.g., #editor-demo)
tags:
  - '#adr'
  - '#agent-removal'
# ISO date format (e.g., 2026-02-06)
date: '2026-03-05'
# Related documents as quoted wiki-links
# (e.g., "[[2026-02-04-feature-research]]")
related:
  - '[[2026-03-05-agent-removal-research]]'
  - '[[2026-03-05-agent-removal-reference]]'
---

# `agent-removal` adr: `Remove obsolete agent management and A2A protocol` | (**status:** `accepted`)

## Problem Statement

The `vaultspec` repository currently contains extensive code for agent management, A2A (Agent-to-Agent) protocol, sub-agents, and team coordination. This functionality has been migrated to the dedicated `vaultspec-a2a` repository. Retaining this obsolete code in the core `vaultspec` repository causes maintenance overhead, confusion, and bloating of the codebase, CLI, and MCP tools.

## Considerations

- The functionality has already been migrated to `vaultspec-a2a`.
- Removing this code will simplify the core `vaultspec` project.
- The removal needs to be comprehensive, touching CLI commands, MCP tools, library code, orchestration logic, and tests.
- We need to ensure that core execution logic that doesn't rely on the A2A protocol remains intact, while safely removing A2A-specific hooks and configurations.

## Constraints

- Ensure no features required by the core `vaultspec` application are accidentally removed.
- All references in `__main__.py`, `spec_cli.py`, configurations, and test suites must be cleaned up to avoid runtime or import errors.

## Implementation

The implementation will involve removing the following components as identified in the research and reference documents:

1. **CLI Commands:** Remove `team`, `subagent`, `server`, and `agents` commands and their associated entry point files (`team_cli.py`, `subagent_cli.py`, `server_cli.py`).
1. **MCP Tools:** Remove `subagent_tools.py` and `team_tools.py` from `src/vaultspec/mcp_server/`.
1. **Library/Orchestration Code:** Remove `core/agents.py`, `orchestration/subagent.py`, `orchestration/team.py`, `orchestration/team_session.py`, `orchestration/team_task_engine.py`.
1. **Protocol Layer:** Delete the entire `src/vaultspec/protocol/a2a/` directory. Remove A2A specific methods like `prepare_process` from `providers/base.py`, `providers/claude.py`, and `providers/gemini.py`.
1. **Core Entry Points:** Update `__main__.py`, `__init__.py`, `spec_cli.py`, `core/enums.py`, and `core/types.py` to remove all references, routing logic, and namespaces related to agents and teams.
1. **Configuration:** Remove `a2a_default_port`, `a2a_host`, `agent_mode`, `agent_dir` and related env variables from `config/config.py`.
1. **Tests:** Remove all tests under `protocol/a2a/tests/`, and specific team/agent tests like `test_team_mixed.py`, `test_team_provider.py`, `test_e2e.py` (A2A parts), and `test_load_agent.py`.

Reference `[[2026-03-05-agent-removal-research]]` and `[[2026-03-05-agent-removal-reference]]` specs.

## Rationale

Migrating agent and team management to a separate repository (`vaultspec-a2a`) enforces a better separation of concerns. The core `vaultspec` repository should focus on its primary mission without being burdened by the complexities of multi-agent orchestration and A2A communication protocols. This removal completes the migration process, streamlining the codebase.

## Consequences

- The core `vaultspec` CLI and package will no longer support agent, subagent, server, or team commands directly. Users must rely on `vaultspec-a2a` for these features.
- The codebase size will decrease, and maintainability will improve.
- The MCP server exposed by `vaultspec` will be leaner, dropping team and subagent tools.

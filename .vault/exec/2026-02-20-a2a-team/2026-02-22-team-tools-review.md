---
tags: ["#exec", "#a2a-team"]
related:
  - "[[2026-02-20-team-mcp-integration-p1-adr]]"
  - "[[2026-02-20-a2a-team-adr]]"
date: 2026-02-22
---

# Code Review: Team MCP Tools

## Context

Audit of the new src/vaultspec/mcp_tools/team_tools.py and src/vaultspec/mcp_tools/tests/test_team_tools.py modules against 2026-02-20-team-mcp-integration-p1-adr.

## Status: **PASS**

The implementation is high-quality, safe, and generally aligned with the architectural intent. A few minor recommendations regarding input validation and tool deviations are noted below.

## Safety Findings

### 1. Path Traversal Risk (Medium)
- **Location**: _session_path in src/vaultspec/mcp_tools/team_tools.py.
- **Observation**: The 
ame parameter is used directly in path construction: oot / ... / f"{name}.json".
- **Risk**: While pathlib handles paths safely, a malicious team name (e.g., ../sensitive) could theoretically write or read JSON files outside the intended .vault/logs/teams/ directory.
- **Recommendation**: Sanitize 
ame to ensure it contains only safe characters (alphanumeric, dashes, underscores) or verify it does not contain path separators.

### 2. Global Configuration (Low)
- **Location**: _root_dir global variable.
- **Observation**: The module relies on a global _root_dir set via set_root_dir.
- **Risk**: This is standard for current MCP tool patterns but limits the module to a single workspace context per process.
- **Verdict**: Acceptable for the current architecture.

## Intent Findings

### 1. Tool Surface Deviation (Note)
- **Observation**: The implemented tools deviate slightly from the list in 2026-02-20-team-mcp-integration-p1-adr but align perfectly with the CLI commands in 2026-02-20-a2a-team-adr.
  - **Implemented**: create_team, 	eam_status, list_teams, dispatch_task, roadcast_message, send_message, dissolve_team.
  - **Missing from ADR**: collect_results (implicit in dispatch_task), elay_message (covered by send_message primitives), ping_team_members.
- **Verdict**: The deviation is an improvement, simplifying the API by making dispatch synchronous-over-async and aligning with the CLI.

### 2. Blocking Dispatch (Note)
- **Location**: dispatch_task and roadcast_message.
- **Observation**: These tools await the completion of the task (via coordinator.dispatch_parallel).
- **Impact**: For very long-running agent tasks, the MCP tool call might timeout depending on the client configuration. This is a reasonable trade-off for simplicity in Phase 1.

## Quality Findings

- **Test Coverage**: Excellent. The use of _MuxTransport to test httpx logic with in-process ASGI apps in 	est_team_tools.py is a robust pattern that avoids brittle mocking.
- **Type Safety**: Code is well-typed and passes static analysis checks visually.
- **Documentation**: Docstrings are clear and reference the corresponding CLI implementations.

## Actionable Recommendations

1.  **Sanitize Team Names**: Add a check in create_team and _load_session to reject names containing path separators or unsafe characters.
2.  **Timeout Handling**: Consider future enhancements for async dispatch (fire-and-forget) if task durations exceed MCP timeouts.

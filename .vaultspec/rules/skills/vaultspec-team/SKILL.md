---
name: vaultspec-team
description: >-
  Form and manage a multi-agent team to perform complex, parallelizable tasks.
  Use this skill when a task is too large for a single sub-agent or benefits
  from specialized agents working in coordination.
---
# Team Coordination Skill (vaultspec-team)

This skill enables the deployment of multiple specialized agents working
together as a team. Use it for massive refactors, multi-module auditing, or
any scenario where parallel execution and peer-to-peer agent communication
(A2A) provide an advantage.

## Usage

### Form a Team

Use the `create_team` tool to assemble specialized agents.

```bash
# Example: Creating a team with a researcher and an auditor
create_team(
  name="feature-x-team",
  agent_urls="localhost:10011, localhost:10012"
)
```

### Dispatch Tasks

Use `dispatch_task` or `broadcast_message` to assign work to team members.

```bash
# Assign a specific task to a team member
dispatch_task(
  team_name="feature-x-team",
  agent_name="vaultspec-researcher",
  task="Analyze the current implementation of module Y."
)
```

### Coordinate & Monitor

- Use `team_status` to track progress and member states.
- Use `send_message` for direct agent-to-agent communication.
- Use `dissolve_team` when the team goal is achieved.

## Tooling Strategy

Teams MUST prioritize the same core repository tools as individual sub-agents:

- **Discovery**: `fd`
- **Search**: `rg`
- **Manipulation**: `sg`
- **Text Processing**: `sd`

## Examples

**Deploy a documentation audit team:**

- `create_team(name="audit-team", agent_urls="...")`
- `broadcast_message(team_name="audit-team", message="Scan .vault/ for broken links.")`
- `team_status(name="audit-team")`

## Behavior

- Team sessions are persisted to `.vault/logs/teams/{name}.json`.
- Communication is handled via the A2A (Agent-to-Agent) protocol over HTTP.
- Spawned processes are tracked by PID for clean dissolution.

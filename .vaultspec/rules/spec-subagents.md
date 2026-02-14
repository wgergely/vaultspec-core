---
name: spec-subagents
---

# Sub-Agents

Sub-agents are the de facto standard for performing any meaningful work. They are invoked using the `spec-subagent` skill.

## Mechanism

This is the **utility skill** that powers the project's agentic workflows.

* **Primary Usage:** You will be instructed to use this skill by high-level workflow skills (e.g., `spec-execute` will tell you to "Invoke `spec-subagent` with `complex-executor`").
* **Direct Usage:** You should only invoke this skill directly if the user explicitly requests a specific, isolated agent dispatch (e.g., "Dispatch the code-reviewer to check file X") that falls outside the standard Research -> Plan -> Execute workflow.

## Internal Dispatch Protocol

Internally, the skill uses `subagent.py`:

```bash
python .vaultspec/scripts/subagent.py run --agent <agent_name> --goal "<task_description|plan_document>"
```

> `--agent`: The name of the agent to load
> `--goal`: A clear, natural language description of the task (or a `<Plan>` document path)
> `--model` (Optional): Override the model

## MCP Server (preferred)

The subagent system is also available as an MCP server (`vs-subagent-mcp`) configured in `.mcp.json`. When available, prefer MCP tool calls over CLI invocation:

* **`list_agents`**: Discover available agents and their capabilities.
* **`dispatch_agent`**: Dispatch a sub-agent with a task. Parameters: `agent` (required), `task` (required), `model` (optional), `mode` (optional: `read-write` or `read-only`).

The MCP server wraps the same ACP dispatch logic and returns structured JSON results.

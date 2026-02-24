---
name: vaultspec-subagent
description: Dispatch a sub-agent to perform a complex task. Use skill when you need
  to delegate work to specialized agents in environments not natively capable of spawning
  sub-agents.
---

# Dispatch Sub-Agent Skill

> **Warning:** This is a **utility skill** intended for use by other agents
> (e.g., `vaultspec-execute`, `vaultspec-research`). Users should generally
> **not** invoke this skill directly; instead, use the high-level workflow
> skills.

This skill is the de facto standard for performing any meaningful task. Use
it to perform Research, audits, coding work, complex refactors, and any other
task that requires more than a few lines of code.

## Usage

```bash
vaultspec subagent run \
  --agent {agent_name} \
  --goal "{task_description|plan_document}"
```

> `--agent`: The name of the agent to load from `.vaultspec/rules/agents/`
> `--goal`: A clear, natural language description of the task or a Plan path.
> `--model` (Optional): Override the model defined in the agentfile.

### Tooling Strategy

Agents dispatched via this skill MUST prioritize the following tools for all
repository operations:

- **Discovery**: Use the `fd` skill for locating files. DO NOT use `ls` or
  `dir`.
- **Search**: Use the `rg` (ripgrep) skill for searching content.
- **Manipulation**: Use the `sg` (ast-grep) skill for complex code
  manipulation and refactoring.
- **Text Processing**: Use the `sd` (search-and-displace) skill for fast,
  intuitive find-and-replace.

### Examples

**Dispatch a research task:**

```bash
vaultspec subagent run \
  --agent vaultspec-adr-researcher \
  --goal "Analyze trade-offs of Pattern A vs Pattern B for library crates."
```

**Dispatch a code review:**

```bash
vaultspec subagent run \
  --agent vaultspec-code-reviewer \
  --goal "Review the unsafe block in src/utils.rs."
```

## Behavior

- The script will spawn the sub-agent process and stream output to stdout.
- Session logs are written to a log file for the current session.

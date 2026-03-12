---
name: vaultspec-team
description: >-
  Form and manage a multi-agent team to perform complex, parallelizable tasks.
  Use this skill when a task is too large for a single agent persona or benefits
  from specialized agents working in coordination.
---
# Team Coordination Skill (vaultspec-team)

This skill defines how to supervise multiple specialized agent personas when a
task is too large for a single worker. Use it for massive refactors,
multi-module auditing, or any scenario where parallel execution and
multi-agent coordination provide an advantage.

## When to Use

- The task spans multiple modules, repositories, or domains.
- Parallel execution would significantly reduce total effort.
- The task benefits from specialized roles (researcher, coder, reviewer)
  working in coordination.

For focused, single-persona work, load the agent persona directly instead.

## Mechanism

This skill is a coordination policy, not a shipped MCP API contract.

- The host environment selects the participating agent personas.
- The host environment assigns task boundaries, context, and sequencing.
- The host environment monitors progress, handles permission prompts, and
  decides when to re-route or stop work.

Use this skill when you need a supervised team shape such as:

- researcher -> author -> editor
- researcher -> executor -> reviewer
- supervisor with multiple parallel specialists

## Tooling Strategy

Teams MUST prioritize the same core repository tools as individual agents:

- **Discovery**: `fd`
- **Search**: `rg`
- **Manipulation**: `sg`
- **Text Processing**: `sd`

## Supervision

The coordination loop remains host-supervised. Do not claim or assume a
shipped MCP team-thread runtime unless the product surface explicitly provides
it.

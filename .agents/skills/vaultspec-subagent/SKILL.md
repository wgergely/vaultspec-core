---
name: vaultspec-subagent
description: Dispatch a sub-agent to perform a complex task. Use skill when you need
  to delegate work to specialized agents in environments not natively capable of spawning
  sub-agents.
---

# vaultspec-subagent

## Purpose

Use this skill to delegate bounded specialist work within the framework. It is
an internal convention for role-based execution, not a promise of any
particular command, service, or transport.

## When to use

- A task benefits from a specialist persona or explicit role separation.
- Another workflow says to invoke `vaultspec-subagent`.
- The handoff needs a named agent identity and a defined result.

## Required handoff

Provide all of the following:

- `agent`: the framework identity or persona to apply
- `goal`: the concrete outcome to produce
- `constraints`: scope, rules, exclusions, and required context
- `expected result`: the artifact, decision, or output to return

## Environment note

Host environments may implement delegation differently, or not at all. Agent
names are framework resource identities, not guaranteed runnable endpoints.

## Fallback

If no delegation mechanism exists, execute the task directly while preserving
the requested role separation. Keep the same agent identity, goal,
constraints, and expected result in the handoff and output.

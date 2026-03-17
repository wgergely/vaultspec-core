---
name: vaultspec-code-research
description: >-
  Skill for grounding coding tasks by researching projects, code snippets,
  reference implementations. Highly recommended for complex feature
  implementation, or where documentatio coverage is insufficient and
  direct source-code referencing is required.
---

# Code Research

Use this skill:

- When auditing, researching, or implementing a specific technical implementation.
- When you need to identify a reference project.
- When need to ground current task with source code references to see
  how reference project achieves feature.
- Ensuring we do not miss implementation aspects or details.
- To ground and de-risk complex coding tasks. Anchoring research with actual code.,

Invoke when `vaultspec-research` -> `vaultspec-adr` -> `vaultspec-write-plan`
explicitly requires direct code referencing.

## Required steps

- **Announce at start:** "I'm using the `vaultspec-code-reference` skill to find
  out how `{Reference}` implements `{Feature}`."
- Use an appropiate parallelized sub-agents, e.g. `vaultspec-code-reference-agent`.
  Instruct them to locate and audit `{Feature}`
  implementation in reference codebase.
- **Must persist findings** to
  `.vault/reference/YYYY-MM-DD-{Feature}-reference.md`."

### Research & Audit (`vaultspec-code-reference-agent`)

Use `vaultspec-code-reference-agent` to perform deep dives.

Coordinate the agents to:

- Locate the code snippets and files.
- Analyze the implementation patterns, architecture, and patterns.
- Persist a Reference blueprint to
  `.vault/reference/YYYY-MM-DD-{Feature}-reference.md`. If file exists
  already, assess and update it.

### Implementation Plan

You MUST check if an implementation exists already. If it does:

- Do our findings alter the implementation? If so report back to user.
- You must explicitly report any possible issues and drifts and leave notes
  in the Plan referencing the `{Feature}` audit to ensure we can address them.

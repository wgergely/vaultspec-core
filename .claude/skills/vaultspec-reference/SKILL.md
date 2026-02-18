---
name: vaultspec-reference
description: Specialized skill for researching or implementing editor features by
  auditing the reference codebase. Coordinates with the `vaultspec-reference-auditor`
  sub-agent which audits and executes coding tasks.
---

# Code Implementation Audit And Reference Skill

Must use when:

- auditing, researching, or implementing a specific technical implementation. Who does this project achieve this feature?
- auditing or researching a codebase to make architectural decisions. How does this project structure its code?
- when we ensure we do not miss implementation aspects or details. Did we implement all the required traits and features?
- auditing or researching codebase for technical details. How does this project optimize this feature?

Invoke when a `vaultspec-research` -> `vaultspec-adr` -> `vaultspec-write` workflow explicitly investigating a reference project or codebase.

**Announce at start:** "I'm using the vaultspec-reference skill to find out how <Reference> implements <Feature>."

## Workflow

Decide if we're researching:

- If researching, invoke the `vaultspec-subagent` skill with `vaultspec-reference-auditor`. Instruct it to "Audit the [topic] implementation in the reference codebase. Persist findings to .vault/reference/YYYY-MM-DD-<Feature>-reference.md."

### Research & Audit (`vaultspec-reference-auditor`)

Invoke the `vaultspec-subagent` skill with `vaultspec-reference-auditor`. Instruct it to perform a deep dive. The sub-agent will:

- Locate the code snippets and files.
- Analyze the implementation patterns, architecture, and patterns.
- Persist a <Reference> blueprint to `.vault/reference/YYYY-MM-DD-<Feature>-reference.md`. If file exists already, assess and update it.

### Implementation Plan

You MUST check if an implementation exist already. If it does:

- Do our findings alter the implementation?
- You must explicitly report any possible issues and drifts and leave notes in the <Plan> referencing the <Feature> audit to ensure we can address them.

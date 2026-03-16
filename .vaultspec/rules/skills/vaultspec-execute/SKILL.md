---
name: vaultspec-execute
description: >-
  Skill to execute implementation plans. Loads specialized agent personas for
  focused work, or coordinates multiple personas through the host environment
  for complex multi-agent execution. Use when you have a plan document to
  execute.
---

# Implementation Plan: Code Writing Skill

Use this skill:
- To begin the execution of an implementation `plan`.
- To ensure code is written by the appropriate agent.


## Required Steps

- This skill MUST be invoked to execute an implementation `.vault/plan` located at
  `.vault/plan/yyyy-mm-dd-{feature}-{phase}-plan.md`.
- Read and parse the Plan to understand the scope, complexity, and specific
  steps
- Read and parse all linked document to understand context for code challange.

## Executor Delegation

Assume the persona of a delegator.
- Use parallel sub-agents, or autonomous agent team to execute complex plans.
- Use appropriate executor agent persona. When the task
needs multiple specialists, coordinate them.
- Always instruct the coders to execute the current plan, and to read grounding
  research, adrs and the `[[...-plan.md]]`.
- Always instruct to "Start with Phase `{X}`."

### Step Execution & Logging

- Execute the plan step-by-step or in logical batches.
- **Coder must write a Step Record** to
  `.vault/exec/yyyy-mm-dd-{feature}/yyyy-mm-dd-{feature}-{phase}-{step}.md`
  for every completed phase.
- **Coder or supervisor must MUST read and use the template** at
  `.vaultspec/rules/templates/exec-step.md`.

### Frontmatter & Tagging Mandate (Artifacts)

Every artifact (Step Record, Summary, Review) MUST strictly adhere to the
following schema:

- **`tags`**: MUST contain **EXACTLY TWO** tags in a YAML list.
  - **Directory Tag**: Exactly `#exec`.
  - *Feature Tag:* Exactly one kebab-case `#{feature}` tag.
  - *Syntax:* `tags: ["#exec", "#feature"]` (Must be quoted strings in a
    list).
- **`related`**: MUST be a YAML list of quoted `"[[wiki-links]]"`.
  - *Constraint:* No relative paths (`../`), no bare strings, no `@ref`.
- **`date`**: MUST use `yyyy-mm-dd` format.
- **No `feature` key**: Use `tags:` exclusively for feature identification.

### Mandatory Code Review

- After an executor completes a step (or the full plan), you MUST invoke the
  `vaultspec-code-review` skill or a relevant code-review skill.
- For code reviews always utilize the `vaultspec-code-reviewer` persona to audit
  for safety, intent, and quality.
- If the reviewer identifies **CRITICAL** or **HIGH** issues, you MUST
  resolve them by loading an executor again before proceeding.

### Finalization & Summary

- Once all implementation and review steps are complete (and the review
  passes), write the consolidated Phase Summary at
  `.vault/exec/yyyy-mm-dd-{feature}/yyyy-mm-dd-{feature}-{phase}-summary.md`.
- **Template**: You MUST read and use the template at
  `.vaultspec/rules/templates/exec-summary.md`.
- Present the final findings, including modified files and safety status, to
  the user.

## Requirements

- **Autonomy**: Do not ask for confirmation between steps unless a significant
  unforeseen blocker occurs.
- **Integrity**: Ensure the safety audit is never skipped.
- **Traceability**: All changes must be mapped to their respective Step
  Records.

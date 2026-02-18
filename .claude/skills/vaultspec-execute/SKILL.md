---
name: vaultspec-execute
description: Skill to execute implementation plans. Delegates to specialized sub-agents
  based on task complexity. Use when you have a plan document to execute.
---

# Spec Execution Skill (vaultspec-execute)

This skill governs the autonomous execution of `<Plan>`s. It ensures that code is written by the appropriate tiered executor, audited for safety, and documented correctly.

## Instructions

### Plan Initiation

- This skill MUST be invoked to execute an implementation `<Plan>` located at `.vault/plan/yyyy-mm-dd-<feature>-<phase>-plan.md`.
- Read and parse the `<Plan>` to understand the scope, complexity, and specific steps.

### Executor Delegation

Invoke the `vaultspec-subagent` skill with the appropriate executor agent. Instruct it to "Execute the plan at [[...-plan.md]]. Start with Phase [X]."

- **Complex Tasks:** `vaultspec-complex-executor` (High Tier). Use for architectural changes or core logic refactors.
- **Standard Tasks:** `vaultspec-standard-executor` (Medium Tier). Use for typical features and components.
- **Simple Tasks:** `vaultspec-simple-executor` (Low Tier). Use for straightforward edits or documentation.

### Step Execution & Logging

- Execute the `<Plan>` step-by-step or in logical batches.
- Ensure the executor writes a `<Step Record>` to `.vault/exec/yyyy-mm-dd-<feature>/yyyy-mm-dd-<feature>-<phase>-<step>.md` for every completed phase.
- **Template**: You MUST read and use the template at `.vaultspec/templates/exec-step.md`.

### Frontmatter & Tagging Mandate (Artifacts)

Every artifact (`Step Record`, `Summary`, `Review`) MUST strictly adhere to the following schema:

- **`tags`**: MUST contain **EXACTLY TWO** tags in a YAML list.
  - **Directory Tag**: Exactly `#exec`.
  - *Feature Tag:* Exactly one kebab-case `#<feature>` tag.
  - *Syntax:* `tags: ["#exec", "#feature"]` (Must be quoted strings in a list).
- **`related`**: MUST be a YAML list of quoted `"[[wiki-links]]"`.
  - *Constraint:* No relative paths (`../`), no bare strings, no `@ref`.
- **`date`**: MUST use `yyyy-mm-dd` format.
- **No `feature` key**: Use `tags:` exclusively for feature identification.

### Mandatory Code Review

- After an executor completes a step (or the full plan), you MUST invoke the `vaultspec-review` skill.
- This will dispatch the `vaultspec-code-reviewer` to audit for safety, intent, and quality.
- If the reviewer identifies **CRITICAL** or **HIGH** issues, you MUST resolve them by dispatching an executor again before proceeding.

### Finalization & Summary

- Once all implementation and review steps are complete (and the review passes), write the consolidated `<Phase Summary>` at `.vault/exec/yyyy-mm-dd-<feature>/yyyy-mm-dd-<feature>-<phase>-summary.md`.
- **Template**: You MUST read and use the template at `.vaultspec/templates/exec-summary.md`.
- Present the final findings, including modified files and safety status, to the user.

## Requirements

- **Autonomy**: Do not ask for confirmation between steps unless a significant unforeseen blocker occurs.
- **Integrity**: Ensure the safety audit is never skipped.
- **Traceability**: All changes must be mapped to their respective `<Step Record>`s.

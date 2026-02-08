---
description: "Skill to execute implementation plans. Delegates to specialized sub-agents based on task complexity. Use when you have a plan document to execute."
---

# Task Execution Skill (task-execute)

This skill governs the autonomous execution of `<Plan>`s. It ensures that code is written by the appropriate tiered executor, audited for safety, and documented correctly.

## Instructions

### 1. Plan Initiation

- This skill MUST be invoked to execute an implementation `<Plan>` located at `.docs/plan/yyyy-mm-dd-<feature>-<phase>-plan.md`.
- Read and parse the `<Plan>` to understand the scope, complexity, and specific steps.

### 2. Executor Delegation

Invoke the `task-subagent` skill with the appropriate executor agent. Instruct it to "Execute the plan at [[...-plan.md]]. Start with Phase [X]."

- **Complex Tasks:** `complex-executor` (High Tier). Use for architectural changes or core logic refactors.
- **Standard Tasks:** `standard-executor` (Medium Tier). Use for typical features and components.
- **Simple Tasks:** `simple-executor` (Low Tier). Use for straightforward edits or documentation.

### 3. Step Execution & Logging

- Execute the `<Plan>` step-by-step or in logical batches.
- Ensure the executor writes a `<Step Record>` to `.docs/exec/yyyy-mm-dd-<feature>/yyyy-mm-dd-<feature>-<phase>-<step>.md` for every completed phase.
- **Template**: You MUST read and use the template at `.rules/templates/EXEC_STEP.md`.

### Frontmatter & Tagging Mandate (Artifacts)

Every artifact (`Step Record`, `Summary`, `Review`) MUST strictly adhere to the following schema:

1. **`tags`**: MUST contain **EXACTLY TWO** tags in a YAML list.
    - **Directory Tag**: Exactly `#exec`.
    - *Feature Tag:* Exactly one kebab-case `#<feature>` tag.
    - *Syntax:* `tags: ["#exec", "#feature"]` (Must be quoted strings in a list).
2. **`related`**: MUST be a YAML list of quoted `"[[wiki-links]]"`.
    - *Constraint:* No relative paths (`../`), no bare strings, no `@ref`.
3. **`date`**: MUST use `yyyy-mm-dd` format.
4. **No `feature` key**: Use `tags:` exclusively for feature identification.

### 4. Mandatory Code Review

- After an executor completes a step (or the full plan), you MUST invoke the `task-review` skill.
- This will dispatch the `code-reviewer` to audit for safety, intent, and quality.
- If the reviewer identifies **CRITICAL** or **HIGH** issues, you MUST resolve them by dispatching an executor again before proceeding.

### 5. Finalization & Summary

- Once all implementation and review steps are complete (and the review passes), write the consolidated `<Phase Summary>` at `.docs/exec/yyyy-mm-dd-<feature>/yyyy-mm-dd-<feature>-<phase>-summary.md`.
- **Template**: You MUST read and use the template at `.rules/templates/EXEC_SUMMARY.md`.
- Present the final findings, including modified files and safety status, to the user.

## Requirements

- **Autonomy**: Do not ask for confirmation between steps unless a significant unforeseen blocker occurs.
- **Integrity**: Ensure the safety audit is never skipped.
- **Traceability**: All changes must be mapped to their respective `<Step Record>`s.

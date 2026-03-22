---
name: vaultspec-write-plan
description: >-
  Use this skill to write implementation plans, task flows. It must be
  explicitly called after a vaultspec-adr skill has yielded an approved ADR
  document.
---

# Write Implementation Skill

Use this skill to:

- Write the required implementation plan grounded with research and ADRs.
- plan **non-trivial work, such as new features, complex auditing, or refactoring**.
- when user explicitly asked to "write task" or "write plan".

This skill **MUST always** be called after `vaultspec-adr` concludes with architectural
approval.

## Important

- If part of the `vaultspec-research` -> `vaultspec-adr` flow, this skill
  **MUST** be provided with the relevant Research and ADR documents.

- If invoked standalone, you must locate or request relevant context.

## Rules

- **Announce:** Explicitly state you are starting the planning phase.

- **Must reference research and ADRs**. Read these in full prior to writing the plan.

- Ensure no knowledge gap remains prior to writing plan. Call vaultspec- research skills
  if more information is needed.

- **Abstraction:** Do **NOT** include granular code details. The plan should outline
  the PHASES, STEPS but not the code. Focus on **what** and **where**.

- **Persistence:**

  - Plans: `.vault/plan/yyyy-mm-dd-{feature}-{phase}-plan.md`

  - Phase Summaries:
    `.vault/exec/yyyy-mm-dd-{feature}/yyyy-mm-dd-{feature}-{phase}-summary.md`

  - Step Records:
    `.vault/exec/yyyy-mm-dd-{feature}/yyyy-mm-dd-{feature}-{phase}-{step}.md`

## Template

- You MUST read and use the template at `.vaultspec/rules/templates/plan.md`.

### Frontmatter & Tagging Mandate

Every document MUST strictly adhere to the following schema:

- **`tags`**: MUST contain **EXACTLY TWO** tags in a YAML list.

  - **Directory Tag**: Exactly `#plan`.
  - **Feature Tag**: Exactly one kebab-case `#{feature}` tag.
  - _Syntax:_ `tags: ["#plan", "#feature"]` (Must be quoted strings in a
    list).

- **`related`**: MUST be a YAML list of quoted `"[[wiki-links]]"`.

  - _Constraint:_ No relative paths (`../`), no bare strings, no `@ref`.

- **`date`**: MUST use `yyyy-mm-dd` format.

- **No `feature` key**: Use `tags:` exclusively for feature identification.

## Workflow

- **Research**: Ensure vaultspec research agents has answered questions.

- **Linking**: Ensure the Plan uses `[[wiki-links]]`.

- **Drafting**: If working with sug-agents use `vaultspec-writer` agent persona.
  Instruct it to "Create an implementation plan for `{feature}` based on
  `[[...-adr.md]]`. Use the template at `.vaultspec/rules/templates/plan.md`."

- **Review**: Present the saved Plan summary to the user before executing.

- **Provide an absolute link** and prompt user:

  ```markdown
  The Plan is ready:
  [[yyyy-mm-dd-{feature}-{phase}-plan.md]]

  Do you want to approve the Plan, or request changes?
  ```

- **Approval Loop**: User must explicitly approve the Plan. If changes are
  requested, load the `vaultspec-writer` agent personaa again to make changes.
  If more research and grounding is required use the appropiate vaultspec research skills
  and agents.
  Instruct them to "Revise the plan based on user feedback: `{feedback}`."

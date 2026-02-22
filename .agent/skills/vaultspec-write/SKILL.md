---
name: vaultspec-write
description: Use this skill to write implementation plans, task flows. It must be
  explicitly called after a vaultspec-adr skill has yielded an approved ADR document.
---

# Spec Write Skill (vaultspec-write)

Use this skill to write task steps for **non-trivial work, such as new
features, complex auditing, or refactoring**. MUST be used when explicitly
prompted to "write task" or "write plan".

This skill MUST be called after `vaultspec-adr` concludes with architectural
approval. Do NOT use for trivial tasks.

## Important

- If part of the `vaultspec-research` -> `vaultspec-adr` flow, this skill
  **MUST** be provided with the relevant Research and ADR documents.
- If invoked standalone, you must locate or request relevant context.

## Rules

- **Announce:** Explicitly state you are starting the planning phase.
- **ADR is King:** ADRs are binding.
- **Research Backs ADR:** Research provides context for the ADR.
- **ADR Backs Implementation:** The Plan must strictly follow the ADR.
- **Discovery:** Use `fd` and `rg` to investigate the current codebase state.
  Do not assume; verify.
- **Abstraction:** Do **NOT** include granular implementation details (code
  snippets) unless requested. Focus on _what_ and _where_.
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

- **Research**: Ensure `vaultspec-adr-researcher` has answered questions.
- **Linking**: Ensure the Plan uses `[[wiki-links]]`.
- **Drafting**: Invoke the `vaultspec-subagent` skill with `vaultspec-writer`.
  Instruct it to "Create an implementation plan for `{feature}` based on
  `[[...-adr.md]]`. Use the template at `.vaultspec/rules/templates/plan.md`."
- **Review**: Present the saved Plan to the user.
- **Provide an absolute link** and prompt user:

  ```markdown
  The Plan is ready:
  [[yyyy-mm-dd-{feature}-{phase}-plan.md]]

  Do you want to approve the Plan, or request changes?
  ```

- **Approval Loop**: User must explicitly approve the Plan. If changes are
  requested, invoke the `vaultspec-subagent` skill with `vaultspec-writer`.
  Instruct it to "Revise the plan based on user feedback: `{feedback}`."

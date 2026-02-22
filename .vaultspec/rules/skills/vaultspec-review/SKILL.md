---
name: vaultspec-review
description: >-
  Skill to conduct a formal code review. Audits code for safety, intent, and
  quality. Mandates dispatching the vaultspec-code-reviewer agent.
---
# Spec Review Skill (vaultspec-review)

When to use this skill:

- **Mandatory:** At the end of every `vaultspec-execute` cycle (before
  marking a feature as "Done").
- **Ad-hoc:** When you need a second pair of eyes on a specific module or PR.
- **Safety Check:** When you suspect a safety violation (e.g., `unsafe`
  usage).

**Announce at start:** "I'm using the `vaultspec-review` skill to audit the
implementation."

## Workflow

### Context Gathering

- Identify the Plan (`.vault/plan/...`) and the specific files modified.

### Dispatch Reviewer

Invoke the `vaultspec-subagent` skill with `vaultspec-code-reviewer`.
Instruct it to:

> "Perform a comprehensive code review of `{feature/files}`. Verify safety
> (no-crash policy), intent (alignment with `[[...-plan.md]]`), and code
> quality. Persist the report to `.vault/exec/...-review.md`."

### Analysis of Report

- **Pass:** If the reviewer finds no critical issues, you may proceed.
- **Fail:** If the reviewer flags issues, you **MUST** invoke
  `vaultspec-execute` (or dispatch an executor) to fix the issues, then
  re-run `vaultspec-review`.

## Persistence

- **Template:** You MUST read and use the template at
  `.vaultspec/rules/templates/code-review.md`.
- **Location:**
  `.vault/exec/yyyy-mm-dd-{feature}/yyyy-mm-dd-{feature}-review.md`.
- **Tags:** Ensure it uses the `#exec` and `#{feature}` tags.

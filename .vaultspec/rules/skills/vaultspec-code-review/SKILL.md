---
name: vaultspec-code-review
description: >-
  Skill to conduct a formal code review. Audits code for safety, intent, and
  quality. Mandates loading the vaultspec-code-reviewer agent persona.
---

# Code Review Skill

When to use this skill:

- **Mandatory:** At the end of every `vaultspec-execute` cycle
- before marking a feature as "Done", or before publishing a PR.
- after major feature implementation work.
- When you need a second pair of eyes on a specific module or PR.
- **Safety Check:** When you suspect a safety violation (e.g., `unsafe`
  usage) or testing framework issue in complex projects.

## Workflow

- **Announce at start:** "I'm using the `vaultspec-code-review` skill to audit the
implementation."
- Identify relevant docs, the plan (`.vault/plan/...`), adr and research documents
- Identify files modified
- Log discovered issues to `.vault/audit/YYYY-MM-DD-{feature}-{review}.md as triaged
  `LOW` -> `CRITICAL` task entries.
- Use a `vaultspec-code-reviewer` agent persona, or other code-review specialists.
- Use parallel subagents to comprehensively comb through codebase.
- Instuct agents to always read grounding docs, adrs and plans
- Instruct agents to use a single shared `.vault/audit/yyyy-mm-dd-{feature}-{review}.md`
  to persist findings as triaged issue logs.
- Code review is not a code fixer skill - do NOT modify the codebase.


## IMPORTANT:

- **Template:** You MUST read and use the template at
  `.vaultspec/rules/templates/code-review.md`.
- **Location:** Must save to
  `.vault/audit/yyyy-mm-dd-{feature}-{review}.md`.
- **Tags:** Ensure persisted audit doc uses the `#audit` and `#{feature}` tags.
- Issues must be continously appended to audit document as a rolling log of
  task queue.

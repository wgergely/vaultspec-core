---
name: vaultspec-curate
description: >-
  Use this skill to audit and clean the .vault vault. Validates frontmatter,
  wiki-links, naming conventions, template compliance, and directory
  structure. Fixes violations in-place and produces an audit report.
---
# Documentation Curation Skill (vaultspec-curate)

This skill governs the autonomous auditing and maintenance of the `.vault/`
documentation vault. It ensures every artifact conforms to the project's
documentation standards as defined in
`.vaultspec/rules/rules/vaultspec-documentation.builtin.md`.

**Announce at start:** "I'm using the `vaultspec-curate` skill to audit and
clean the documentation vault."

## When to Use

- After completing a feature (post `vaultspec-execute`) to verify
  documentation trail integrity.
- Periodically as vault hygiene maintenance.
- When broken links, missing frontmatter, or organizational drift is
  suspected.
- Before onboarding a new feature to ensure the vault baseline is clean.

## Workflow

### Dispatch the Curator

Invoke the `vaultspec-subagent` skill with `vaultspec-docs-curator`. Instruct
it to "Perform a full vault audit of `.vault/`. Validate frontmatter,
wiki-links, naming conventions, template compliance, and directory structure.
Fix violations in-place and produce an audit report."

For targeted audits, scope the task accordingly
(e.g., "Audit only `.vault/exec/...`").

### Review the Audit Report

The curator persists its findings to:

`.vault/exec/yyyy-mm-dd-docs-curation/yyyy-mm-dd-docs-curation-audit.md`

Review the report for:

- **Auto-fixed** items (renames, link corrections, frontmatter additions).
- **Flagged** items requiring author input (missing template sections,
  ambiguous file placement).

### Act on Flagged Items

Items the curator cannot auto-fix are listed under **Recommendations**.
Address these manually or dispatch the appropriate agent (e.g.,
`vaultspec-simple-executor` for adding missing sections).

## Artifact Linking

- Any persisted markdown files must be linked against other persisted
  documents using quoted `"[[wiki-links]]"`.
- DO NOT use `@ref` style links or `[label](path)` style links.

### Frontmatter & Tagging Mandate

Every document MUST strictly adhere to the following schema:

- **`tags`**: MUST contain **EXACTLY TWO** tags in a YAML list.
  - **Directory Tag**: Exactly one of `#adr`, `#audit`, `#exec`, `#plan`,
    `#reference`, or `#research` (based on file location).
  - **Feature Tag**: Exactly one kebab-case `#{feature}` tag.
  - *Syntax:* `tags: ["#doc-type", "#feature"]` (Must be quoted strings in a
    list).
- **`related`**: MUST be a YAML list of quoted `"[[wiki-links]]"`.
  - *Constraint:* No relative paths (`../`), no bare strings, no `@ref`.
- **`date`**: MUST use `yyyy-mm-dd` format.
- **No `feature` key**: Use `tags:` exclusively for feature identification.

## Requirements

- **Non-destructive**: The curator never deletes files. It renames, edits
  frontmatter/links, and flags.
- **Traceability**: Every modification is logged in the audit report.
- **Standards-first**: All fixes trace back to rules in
  `.vaultspec/rules/rules/vaultspec-documentation.builtin.md` and the canonical
  templates.

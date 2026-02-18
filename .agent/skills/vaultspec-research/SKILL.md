---
name: vaultspec-research
description: Use it when unsure about how to proceed with a complex feature, refactor,
  or debugging task and need to explore options before implementation, structured
  research and brainstorm.
---

# Research & Brainstorm Skill (vaultspec-research)

When to use this skill:

- Before implementing non-trivial features.
- When unsure about major design decisions.
- Before refactors with unclear scope.
- Before debugging complex issues.
- When you need user input on design options.

**Announce at start:** "I'm using the `vaultspec-research` skill to conduct structured research and brainstorming."

**Save findings to:** `<Research>` (`.vault/research/yyyy-mm-dd-<feature>-<phase>-research.md`)

**Dispatch sub-agent:** Invoke the `vaultspec-subagent` skill with `vaultspec-adr-researcher`. Instruct it to "Conduct research on [topic]. Persist findings to .vault/research/..."

## Template

- You MUST read and use the template at `.vaultspec/templates/research.md`.

### Frontmatter & Tagging Mandate

Every document MUST strictly adhere to the following schema:

- **`tags`**: MUST contain **EXACTLY TWO** tags in a YAML list.
  - **Directory Tag**: Exactly `#research`.
  - **Feature Tag**: Exactly one kebab-case `#<feature>` tag.
  - *Syntax:* `tags: ["#research", "#feature"]` (Must be quoted strings in a list).
- **`related`**: MUST be a YAML list of quoted `"[[wiki-links]]"`.
  - *Constraint:* No relative paths (`../`), no bare strings, no `@ref`.
- **`date`**: MUST use `yyyy-mm-dd` format.
- **No `feature` key**: Use `tags:` exclusively for feature identification.

## Workflow

- Research & brainstorm might be followed by:
  - User approval -> proceed with `vaultspec-adr` to create and persist `<ADR>`.
  - No approval -> prompt user to refine goal/constraints and re-run research.

## Artifact Linking

- Any persisted markdown files must be linked against other persisted documents using `[[wiki-links]]`.
- DO NOT use `@ref` style links.
- DO NOT use `[label](path)` style links for internal wiki pages.

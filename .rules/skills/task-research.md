---
description: "Use it when unsure about how to proceed with a complex feature, refactor, or debugging task and need to explore options before implementation, structured research and brainstorm."
---

# Research & Brainstorm Skill (task-research)

When to use this skill:

- Before implementing non-trivial features.
- When unsure about major design decisions.
- Before refactors with unclear scope.
- Before debugging complex issues.
- When you need user input on design options.

**Announce at start:** "I'm using the `task-research` skill to conduct structured research and brainstorming."

**Save findings to:** `<Research>` (`.docs/research/yyyy-mm-dd-<feature>-<phase>-research.md`)

**Dispatch sub-agent:** Invoke the `task-subagent` skill with `adr-researcher`. Instruct it to "Conduct research on [topic]. Persist findings to .docs/research/..."

## Template

- You MUST read and use the template at `.rules/templates/RESEARCH.md`.

### Frontmatter & Tagging Mandate

Every document MUST strictly adhere to the following schema:

1. **`tags`**: MUST contain **EXACTLY TWO** tags in a YAML list.
    - **Directory Tag**: Exactly `#research`.
    - **Feature Tag**: Exactly one kebab-case `#<feature>` tag.
    - *Syntax:* `tags: ["#research", "#feature"]` (Must be quoted strings in a list).
2. **`related`**: MUST be a YAML list of quoted `"[[wiki-links]]"`.
    - *Constraint:* No relative paths (`../`), no bare strings, no `@ref`.
3. **`date`**: MUST use `yyyy-mm-dd` format.
4. **No `feature` key**: Use `tags:` exclusively for feature identification.

## Workflow

- Research & brainstorm might be followed by:
  - User approval -> proceed with `task-adr` to create and persist `<ADR>`.
  - No approval -> prompt user to refine goal/constraints and re-run research.

## Artifact Linking

- Any persisted markdown files must be linked against other persisted documents using `[[wiki-links]]`.
- DO NOT use `@ref` style links.
- DO NOT use `[label](path)` style links for internal wiki pages.

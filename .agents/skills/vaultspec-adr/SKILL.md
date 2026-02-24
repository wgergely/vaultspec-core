---
name: vaultspec-adr
description: Use this skill to persist Architecture Decision Records (ADRs) after
  completing research. ADRs document significant architectural choices, their context,
  and consequences.
---

# Architecture Decision Record (ADR) Skill

When to use this skill:

- After a `vaultspec-research` session has concluded with a recommendation.
- When a significant architectural decision is made that affects the
  project's direction.
- To document the "why" behind major technical choices.

**Announce at start:** "I'm using the `vaultspec-adr` skill to create and
persist an ADR."

**Save ADR to:**
`.vault/adr/yyyy-mm-dd-{feature}-{phase}-adr.md`

**Read and link related Research from:**
`.vault/research/yyyy-mm-dd-{feature}-{phase}-research.md`.
Terminate if related Research is not found and prompt user to first invoke
`vaultspec-research`.

## Template

- You MUST read and use the template at `.vaultspec/rules/templates/adr.md`.

### Frontmatter & Tagging Mandate

Every document MUST strictly adhere to the following schema:

- **`tags`**: MUST contain **EXACTLY TWO** tags in a YAML list.
  - **Directory Tag**: Exactly `#adr`.
  - **Feature Tag**: Exactly one kebab-case `#{feature}` tag.
  - *Syntax:* `tags: ["#adr", "#feature"]` (Must be quoted strings in a
    list).
- **`related`**: MUST be a YAML list of quoted `"[[wiki-links]]"`.
  - *Constraint:* No relative paths (`../`), no bare strings, no `@ref`.
- **`date`**: MUST use `yyyy-mm-dd` format.
- **No `feature` key**: Use `tags:` exclusively for feature identification.

## Workflow

- **Derive from Research:** ADRs should always be preceded by a
  `vaultspec-research` session.
- **Dispatch Sub-Agent:** Invoke the `vaultspec-subagent` skill with
  `vaultspec-writer`. Instruct it to "Draft an ADR for `{feature}` based on
  the findings in `[[...-research.md]]`. Use the template at
  `.vaultspec/rules/templates/adr.md`."
  - *Alternatives:* `vaultspec-adr-researcher` (if the research phase was
    skipped or needs synthesis).
- **Linking:** Use `[[wiki-links]]` for references. DO NOT use `@ref` or
  `[label](path)`.

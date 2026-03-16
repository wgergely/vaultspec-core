---
name: vaultspec-adr
description: >-
  Use this skill to persist Architecture Decision Records (ADRs) after
  completing research. ADRs document significant architectural choices,
  their context, and consequences.
---

# ADR: Architecture Decision Record Writing Skill

Use this skill:
- After a `vaultspec-research` session has concluded with a recommendation.
- When multiple competing technical choices need a grounding document.
- When a significant architectural decision is made that affects the
  project's fundations, feature set, or development trajectory.
- To document the blast radius, "why", "what" of major architectural choices.

## Required steps

  - **Announce at start:** "I'm using the `vaultspec-adr` skill to create a new ADR."
  - **You MUST read and use the template** at `.vaultspec/rules/templates/adr.md`.
  - **MUST save document to:** `.vault/adr/yyyy-mm-dd-{feature}-{phase}-adr.md`
  - **Read and link related Research from:** `.vault/research/yyyy-mm-dd-{feature}-{phase}-research.md`.
  - **Terminate if related research is not found** and prompt user to first invoke `vaultspec-research`.

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

- **Derive from Ressearch:** ADRs should always be preceded by a
  `vaultspec-research` session.
- **CRITICAL: you MUST always** present adr findings as an interactive prompt
  for user approval. Without explicit user sign-off the ADR is considere null and void.
- **Draft ADR using an appropiate agent persona**, like `vaultspec-writer`
- Associate ADR with `{feature}` based on the findings in `[[...-research.md]]`.
- **Linking:** Use `[[wiki-links]]` for references. DO NOT use `@ref` or
  `[label](path)`.

---
name: vaultspec-skills
---

# Spec Skills

This project follows agent-driven development with
`<ADR>`-backed `<Plan>`s.

The workflow persists the following documents:

- `.vault/plan/yyyy-mm-dd-<feature>-<phase>-plan.md`:
  The `<Plan>` to execute.

- `.vault/research/yyyy-mm-dd-<feature>-<phase>-research.md`:
  The `<Research>` findings.

- `.vault/adr/yyyy-mm-dd-<feature>-<phase>-adr.md`:
  Research-derived `<ADR>`.

- `.vault/reference/yyyy-mm-dd-<feature>-reference.md`:
  The implementation `<Reference>`.

- `.vault/audit/yyyy-mm-dd-<feature>-audit.md`:
  The `<Audit>` report.

- `.vault/exec/yyyy-mm-dd-<feature>/.../<step>.md`:
  The individual `<Step Record>`.

- `.vault/exec/yyyy-mm-dd-<feature>/...-summary.md`:
  The `<Phase Summary>`.

Where appropriate, use the following skills:

- `vaultspec-research`
- `vaultspec-code-research`
- `vaultspec-adr`
- `vaultspec-code-reference`
- `vaultspec-write-plan`
- `vaultspec-execute`
- `vaultspec-documentation`

## Documentation Hierarchy

The documentation trail follows a strict dependency graph.
Artifacts lower in the hierarchy should reference those above them.

- **Brainstorm** / **Research / Reference Audit**
  (`.vault/research/`, `.vault/reference/`)

- **Architecture Decision Records (ADR)** (`.vault/adr/`)

  - *Depends on:* brainstorm, research, audits

- **Implementation Plans** (`.vault/plan/`)

  - *Depends on:* ADRs, research, audits, (previous or related feature plans)

- **Execution Records**
  (`.vault/exec/{yyyy-mm-dd-feature}/{yyyy-mm-dd-feature-phase-step}.md`)

  - *Depends on:* Plans.
  - *References:* The Plan being executed.
  - *Location:* Inside feature-specific folder
  - *Filename:* `{yyyy-mm-dd-feature-phase-step}.md`
  - *Example:*
    `.vault/exec/2026-02-04-editor-demo/2026-02-04-editor-demo-phase1-task1.md`

- **Summaries**
  (`.vault/exec/{yyyy-mm-dd-feature}/{yyyy-mm-dd-feature-phase-summary}.md`)

  - *Depends on:* Execution Logs.
  - *References:* The Plan and key Artifacts produced.
  - *Location:* Inside feature-specific folder
  - *Filename:* `{yyyy-mm-dd-feature-phase-summary}.md`
  - *Example:*
    `.vault/exec/2026-02-04-editor-demo/2026-02-04-editor-demo-phase1-summary.md`

## Must follow

- We **ALWAYS** use **Obsidian-style Wiki Links** for internal documentation.

- **Always** populate the `related:` field in the YAML frontmatter with
  `"[[wiki-links]]"` (quoted as strings).

- **Never** use relative paths (`../`) in wiki links; assume a flat namespace
  or vault-root resolution.

- **Always** check if a referenced file exists before linking (if possible).

- **Always** include the relevant `#{feature}` tag in the YAML frontmatter
  using the `tags:` field.

- **Always** use the `tags:` field (not `feature:`) with the format
  `tags: "#{feature}"`.

- **Always** quote wiki-links in YAML: `- "[[file-name]]"` or
  `related: "[[file-name]]"`.

## Tag Taxonomy

**ALLOWED TAGS - DO NOT REMOVE - REFERENCE:**
`#adr` `#audit` `#exec` `#plan` `#reference` `#research` `#{feature}`

Every document in `.vault/` MUST include **EXACTLY TWO** tags in the
frontmatter `tags:` field:

- **Directory Tag**: Based on the `.vault/` subfolder location
  (`#adr`, `#audit`, `#exec`, `#plan`, `#reference`, `#research`)

- **Feature Tag**: Groups related documents across the feature lifecycle
  (kebab-case, e.g., `#editor-demo`)

**CRITICAL:** No structural tags like `#step`, `#summary`, `#phase*`, or
`#design` are allowed. Only the 6 tags listed above.

### Directory Tags (Required for ALL documents)

The directory tag is determined by the file's location in `.vault/`:

| Directory           | Tag          | Description                           |
| :------------------ | :----------- | :------------------------------------ |
| `.vault/adr/`       | `#adr`       | Architecture Decision Records         |
| `.vault/audit/`     | `#audit`     | Audit reports and assessments         |
| `.vault/exec/`      | `#exec`      | Execution records (steps & summaries) |
| `.vault/plan/`      | `#plan`      | Implementation plans                  |
| `.vault/reference/` | `#reference` | Reference audits and blueprints       |
| `.vault/research/`  | `#research`  | Research and brainstorming            |

### Tag Format

All documents use YAML list syntax with at least 2 tags (one directory tag,
one feature tag; additional tags are allowed):

```yaml
---

# REQUIRED TAGS (minimum 2): one directory tag + one feature tag

# DIRECTORY TAGS: #adr #audit #exec #plan #reference #research

tags:

  - "#plan"           # directory tag (based on file location)
  - "#feature-name"   # feature tag (kebab-case)
date: 2026-02-06
related:

  - "[[related-file]]"
---
```

**Examples:**

- Plan file: `tags: ["#plan", "#editor-demo"]`
- ADR file: `tags: ["#adr", "#editor-demo"]`
- Exec step: `tags: ["#exec", "#editor-demo"]`
- Exec summary: `tags: ["#exec", "#editor-demo"]`
- Research: `tags: ["#research", "#text-layout"]`
- Reference: `tags: ["#reference", "#text-layout"]`

### Feature Tags

Feature tags use kebab-case and group all documents related to a specific
feature or work stream:

- Format: `#{feature}` (e.g., `#live-preview-blocks`, `#grid-layout`,
  `#syntax-highlighting`)

- Must be consistent across all documents in the feature's lifecycle

- Always quoted in YAML

## Placeholder Naming Conventions

Templates use curly-brace placeholders `{...}` to indicate values that must
be replaced. Follow these conventions:

### Frontmatter Placeholders

| Placeholder      | Format                | Example                   |
| :--------------- | :-------------------- | :------------------------ |
| `{feature}`      | lowercase, kebab-case | `editor-demo`             |
| `{yyyy-mm-dd}`   | lowercase, ISO 8601   | `2026-02-06`              |
| `{yyyy-mm-dd-*}` | lowercase pattern     | `2026-02-04-feature-plan` |

### Document Body Placeholders

All placeholders use **lowercase, kebab-case** format:

| Placeholder | Format     | Example                  |
| :---------- | :--------- | :----------------------- |
| `{feature}` | kebab-case | `editor-demo`            |
| `{phase}`   | kebab-case | `phase-1`, `phase-2`     |
| `{topic}`   | kebab-case | `event-handling`         |
| `{title}`   | kebab-case | `displaymap-integration` |
| `{step}`    | kebab-case | `task-1-window-setup`    |

### General Rules

- **YAML frontmatter**: Always lowercase, kebab-case

- **Document titles/headings**: Always lowercase, kebab-case
  (e.g., `# editor-demo phase-1 plan`)

- **File names**: lowercase, kebab-case with patterns:

  - Top-level docs: `yyyy-mm-dd-{feature}-{type}.md`
    (e.g., `2026-02-04-editor-demo-plan.md`)

  - Exec steps: `yyyy-mm-dd-{feature}-{phase}-{step}.md`
    inside `.vault/exec/yyyy-mm-dd-{feature}/` folder

  - Exec summaries: `yyyy-mm-dd-{feature}-{phase}-summary.md`
    inside feature folder

- **Replace ALL placeholders**: No template should be committed with `{...}`
  placeholders remaining

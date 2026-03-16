---
tags:
  - "#research"
  - "#skill-audit"
date: "2026-02-22"
---
# Skill Audit and Compliance Research

## Context
The project uses a set of agent skills defined in `.vaultspec/rules/skills`. These skills must comply with the official [Agent Skills specification](https://agentskills.io/specification). A recent audit revealed significant deviations from the standard, particularly regarding directory structure and metadata.

## Audit Findings

### 1. Structural Violations
**Requirement:** The Agent Skills specification (v1.0) mandates that a skill must be a **directory** containing at least a `SKILL.md` file.
**Current State:** Skills in `.vaultspec/rules/skills` are implemented as flat Markdown files (e.g., `vaultspec-adr.md`).

| Skill | Current Path | Compliant Path | Status |
| :--- | :--- | :--- | :--- |
| `vaultspec-adr` | `.../skills/vaultspec-adr.md` | `.../skills/vaultspec-adr/SKILL.md` | 🔴 Fail |
| `vaultspec-curate` | `.../skills/vaultspec-curate.md` | `.../skills/vaultspec-curate/SKILL.md` | 🔴 Fail |
| `vaultspec-execute` | `.../skills/vaultspec-execute.md` | `.../skills/vaultspec-execute/SKILL.md` | 🔴 Fail |
| `vaultspec-research` | `.../skills/vaultspec-research.md` | `.../skills/vaultspec-research/SKILL.md` | 🔴 Fail |
| `vaultspec-write-plan` | `.../skills/vaultspec-write-plan.md` | `.../skills/vaultspec-write-plan/SKILL.md` | 🔴 Fail |
| *(All others)* | `.../*.md` | `.../*/SKILL.md` | 🔴 Fail |

### 2. Metadata Violations
**Requirement:** The YAML frontmatter of `SKILL.md` **must** contain a `name` field that matches the directory name (kebab-case, 1-64 characters).
**Current State:** The flat Markdown files contain `description` but lack the `name` field.

**Example Violation (`vaultspec-adr.md`):**
```yaml
# Current
---
description: Use this skill to persist Architecture Decision Records...
---
```

**Required Correction:**
```yaml
# Compliant
---
name: vaultspec-adr
description: Use this skill to persist Architecture Decision Records...
---
```

### 3. Progressive Disclosure & Prompt Integration
**Requirement:** The system must be able to load only the metadata (name, description) for the system prompt, and load the full instruction text only when the skill is activated.
**Implication:** The `skills-ref` reference implementation generates the `<available_skills>` block by iterating over *directories* and reading `SKILL.md`. The current flat-file structure is incompatible with standard tooling that expects the directory pattern.

### 4. File References
**Requirement:** Resources should be referenced relative to the skill root.
**Current State:** As flat files, they cannot easily reference auxiliary resources (scripts, templates) without cluttering the main `skills/` directory. Moving to a directory structure allows for cleanly scoped `assets/` or `scripts/` subdirectories per skill.

## Recommendations

1.  **Refactor Directory Structure:**
    *   Create a subdirectory for each skill matching its name (e.g., `vaultspec-adr/`).
    *   Move the content of the flat `.md` file to `SKILL.md` within that directory.

2.  **Update Metadata:**
    *   Inject the `name: <skill-name>` field into the frontmatter of every `SKILL.md`.

3.  **Update References:**
    *   Ensure any internal links or system prompt generators are updated to point to the new locations. (Note: The `.gemini` folder seems to already have a compliant structure, implying a potential sync or build process exists, or it's a separate copy. We must ensure `.vaultspec` is the compliant source of truth).

## Validation Plan
After refactoring, validation can be performed using the `skills-ref` library:
```bash
skills-ref validate .vaultspec/rules/skills/vaultspec-adr
```
This will confirm adherence to the spec.

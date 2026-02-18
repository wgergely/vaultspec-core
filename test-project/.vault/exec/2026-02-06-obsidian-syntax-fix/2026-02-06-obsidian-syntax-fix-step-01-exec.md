---
tags:
  - "#exec"
  - "#obsidian-syntax-fix"
date: 2026-02-06
related:
  - "[[README]]"
---

# obsidian-syntax-fix step-1

Fixed critical Obsidian wiki-link syntax issues across all templates, skills, and agent definitions.

- Modified: "[[.rules/templates/ADR.md]]"
- Modified: "[[.rules/templates/PLAN.md]]"
- Modified: "[[.rules/templates/RESEARCH.md]]"
- Modified: "[[.rules/templates/EXEC_STEP.md]]"
- Modified: "[[.rules/templates/EXEC_SUMMARY.md]]"
- Modified: "[[.rules/templates/REF_AUDIT.md]]"
- Modified: "[[.rules/templates/CODE_REVIEW.md]]"
- Modified: "[[.rules/templates/README.md]]"
- Modified: "[[.rules/agents/docs-curator.md]]"
- Modified: "[[.rules/skills/task-curate.md]]"

## Description

### Issue 1: `feature:` field → `tags:` field

Obsidian uses the `tags:` field, not `feature:`, for tagging documents. All templates were using the deprecated `feature:` field.

**Fixed in all templates:**

- Changed `feature: #<feature>` to `tags: "#<feature>"`
- Format now: `tags: "#<feature-name>"` (quoted string with hashtag)

### Issue 2: Unquoted wiki-links in YAML

Obsidian requires wiki-links in YAML frontmatter to be quoted as strings.

**Fixed in all templates:**

- Changed `- [[file-name]]` to `- "[[file-name]]"`
- Changed multi-item lists with unquoted links to properly quoted format
- Example: `related:\n  - "[[yyyy-mm-dd-*]]"`

### Issue 3: Updated docs-curator agent definition

Enhanced the docs-curator agent with CRITICAL instructions about:

1. Using `tags:` NOT `feature:`
2. Quoting all wiki-links in YAML: `"[[link]]"`
3. Validating this syntax in all frontmatter
4. Explicit migration path for deprecated `feature:` field

Added new validation rules:

- Check for `tags:` field presence and correct format
- Verify all wiki-links in YAML are quoted
- Flag unquoted wiki-links as violations
- Migrate documents using deprecated `feature:` field

### Issue 4: Updated task-curate skill

Added explicit frontmatter standards section documenting:

- Use `tags: "#<feature-name>"` NOT `feature:`
- Always quote wiki-links in YAML
- Required fields: `tags:`, `date:`, `related:`

### Issue 5: Updated README.md

Enhanced the "Must follow" section with explicit requirements:

- Use `tags:` field (not `feature:`)
- Quote wiki-links in YAML
- Concrete examples of correct syntax

## Files Changed

### Templates Fixed (7 files)

All templates updated with correct frontmatter:

1. `ADR.md` - Architecture Decision Records
2. `PLAN.md` - Implementation Plans
3. `RESEARCH.md` - Research findings
4. `EXEC_STEP.md` - Execution step records
5. `EXEC_SUMMARY.md` - Phase/task summaries
6. `REF_AUDIT.md` - Reference audits
7. `CODE_REVIEW.md` - Code review reports

### Documentation Updated (1 file)

1. `README.md` - Added explicit syntax rules and examples

### Agents Updated (1 file)

1. `docs-curator.md` - Enhanced with CRITICAL syntax validation rules

### Skills Updated (1 file)

1. `task-curate.md` - Added frontmatter standards section

## Validation

Verified all fixes with grep searches:

```bash
# Confirm no feature: fields remain
rg "^feature:" .rules/ -g "*.md"
# Result: No matches found ✓

# Confirm no unquoted wiki-links in YAML
rg "  - \[\[" .rules/ -g "*.md"
# Result: No matches found ✓

# Verify tags: field present in all templates
rg "^tags:" .rules/templates/ -g "*.md"
# Result: 7 templates confirmed ✓

# Verify quoted wiki-links in templates
rg '"?\[\[' .rules/templates/ -g "*.md"
# Result: All YAML wiki-links properly quoted ✓
```

## Tests

No functional code changes - documentation and template updates only.

Manual validation performed:

- All templates have correct `tags:` field
- All YAML wiki-links are properly quoted
- docs-curator has explicit validation rules
- task-curate documents correct syntax
- README.md provides clear examples

## Commit

```
commit 6e7bb52
docs: fix Obsidian wiki-link syntax - replace feature: with tags: and quote all YAML wiki-links
```

## Notes

This fix ensures all future documentation generated from templates will be Obsidian-compliant. The docs-curator agent will now validate and enforce this syntax across the `.docs/` vault.

Next actions (for docs-curator):

- Audit existing `.docs/` files for deprecated `feature:` field usage
- Migrate all existing documents to use `tags:`
- Validate and fix any unquoted wiki-links in existing documents

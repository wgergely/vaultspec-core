---
tags:
  - '#exec'
  - '#docs-curation'
date: '2026-02-21'
related:
---

# docs-curation audit: 2026-02-21

Vault audit scoped to three untracked files in the `team-mcp-integration` feature
pipeline. All violations were auto-fixed in-place. No files were renamed. No data
was lost.

- Modified: `2026-02-20-team-mcp-integration-p1-adr`
- Modified: `2026-02-20-team-mcp-surface-design-reference`
- Modified: `2026-02-20-team-mcp-integration-research`

## Scope

Files audited:

- `.vault/adr/2026-02-20-team-mcp-integration-p1-adr.md`
- `.vault/reference/2026-02-20-team-mcp-surface-design-reference.md`
- `.vault/research/2026-02-20-team-mcp-integration-research.md`

Standards applied:

- `.vaultspec/rules/rules/vaultspec-documentation.builtin.md`
- `.vaultspec/rules/templates/adr.md`
- `.vaultspec/rules/templates/ref-audit.md`
- `.vaultspec/rules/templates/research.md`

## Findings

### File 1: `.vault/adr/2026-02-20-team-mcp-integration-p1-adr.md`

**Filename:** Compliant. Pattern `yyyy-mm-dd-<feature>-<phase>-adr.md` satisfied.
**Directory placement:** Correct (`.vault/adr/`).
**Tag count:** 2 — compliant.
**Tag values:** `"#adr"`, `"#team-mcp-integration"` — compliant.
**Wiki-link target:** `2026-02-20-team-mcp-integration-research.md` exists — valid.

Violations found and fixed:

| Class | Violation                                                                               | Fix Applied                               |
| ----- | --------------------------------------------------------------------------------------- | ----------------------------------------- |
| A     | Missing mandatory comment block (`# ALLOWED TAGS - DO NOT REMOVE` / `# REFERENCE: ...`) | Inserted two comment lines before `tags:` |
| A     | `date` value quoted as `"2026-02-20"` (string) instead of bare scalar                   | Changed to `date: 2026-02-20`             |

______________________________________________________________________

### File 2: `.vault/reference/2026-02-20-team-mcp-surface-design-reference.md`

**Filename:** Compliant. Pattern `yyyy-mm-dd-<feature>-reference.md` satisfied.
**Directory placement:** Correct (`.vault/reference/`).

Violations found and fixed:

| Class | Violation                                                                              | Fix Applied                                                                               |
| ----- | -------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| A     | Unsupported frontmatter key `title`                                                    | Removed from frontmatter; migrated to body as `**Title:**`                                |
| A     | Unsupported frontmatter key `subtitle`                                                 | Removed from frontmatter; migrated to body as `**Subtitle:**`                             |
| A     | Unsupported frontmatter key `authors` (nested object)                                  | Removed from frontmatter; migrated to body as `**Author:**`                               |
| A     | Unsupported frontmatter key `references` (list of paths)                               | Removed from frontmatter; migrated to body as `**References:**`                           |
| A     | Missing mandatory comment block                                                        | Inserted two comment lines before `tags:`                                                 |
| A     | Missing `related` field entirely                                                       | Added `related:` list                                                                     |
| B     | `tags` contained 4 invalid unquoted tags: `mcp`, `team`, `a2a`, `surface-design`       | Replaced with `["#reference", "#team-mcp-integration"]`                                   |
| C     | `related` absent; `references` listed `.vault/adr/2026-02-20-a2a-team-adr.md` (exists) | Added `"`2026-02-20-a2a-team-adr`"` to `related`; code path refs omitted (not vault docs) |

Data migration note: the `title`, `subtitle`, `authors`, and `references` values were
placed in a `<!-- Migrated from frontmatter -->` comment block immediately after the
closing frontmatter `---`, before the document's first heading. No content was deleted.

______________________________________________________________________

### File 3: `.vault/research/2026-02-20-team-mcp-integration-research.md`

**Filename:** Compliant. Pattern `yyyy-mm-dd-<feature>-research.md` satisfied.
**Directory placement:** Correct (`.vault/research/`).

Violations found and fixed:

| Class | Violation                                                                                        | Fix Applied                                                           |
| ----- | ------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------- |
| A     | Unsupported frontmatter key `title`                                                              | Removed from frontmatter; migrated to body as `**Title:**`            |
| A     | Unsupported frontmatter key `status`                                                             | Removed from frontmatter; migrated to body as `**Status:**`           |
| A     | Missing mandatory comment block                                                                  | Inserted two comment lines before `tags:`                             |
| A     | Missing `related` field entirely                                                                 | Added `related:` list                                                 |
| B     | `tags` used YAML flow/bracket syntax `[team, mcp, integration, audit]` — 4 unquoted invalid tags | Replaced with block-list `["#research", "#team-mcp-integration"]`     |
| C     | Body contained `2026-02-20-team-mcp-surface-design-reference` (target exists); not in `related`  | Added `"`2026-02-20-team-mcp-surface-design-reference`"` to `related` |

Data migration note: `title` and `status` values were placed in a
`<!-- Migrated from frontmatter -->` block before the document's first heading.
Body wiki-link in the Linked Artifacts section left as bare `...` in markdown
body — this is correct; quoting is only required inside YAML frontmatter.

## Recommendations

No items require author input. All violations were deterministically resolvable:

- Tag replacements used the directory location to derive the correct directory tag and
  the `team-mcp-integration` feature slug was unambiguous from the filenames.

- Wiki-link targets were verified against the live `.vault/` file index before
  inclusion in `related`.

- Code path references (`.vaultspec/lib/src/...`, `.vaultspec/lib/scripts/...`) in
  the reference file's original `references` key are not vault documents and were
  correctly excluded from the `related` field. They are preserved in the body.

## Tests

Post-fix verification confirmed for all three files:

- Frontmatter opens with `---`
- Mandatory comment block (`# ALLOWED TAGS - DO NOT REMOVE` + `# REFERENCE: ...`) present
- Exactly 2 tags, both quoted strings, correct directory tag + `#team-mcp-integration`
- `date: 2026-02-20` as unquoted YAML scalar
- `related:` present as a YAML block list of quoted wiki-links
- No unsupported keys (`title`, `subtitle`, `authors`, `references`, `status`, `feature`)
- Frontmatter closes with `---`
- All `related` wiki-link targets confirmed to exist in `.vault/`

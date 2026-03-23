---
tags:
  - '#adr'
  - '#install-cmds'
date: '2026-03-16'
related:
  - '[[2026-03-16-managed-content-blocks-research]]'
  - '[[2026-03-15-install-cmds-capability-audit]]'
  - '[[2026-03-15-claude-code-provider-research]]'
  - '[[2026-03-15-gemini-cli-provider-research]]'
  - '[[2026-03-16-antigravity-provider-research]]'
  - '[[2026-03-16-binding-decisions-research]]'
---

# Managed content blocks ADR: `<vaultspec>` tag system | (**status:** `accepted`)

## Problem Statement

vaultspec-core syncs generated content (framework configuration, rule
references, agent definitions) into files that users also edit directly:
`CLAUDE.md`, `GEMINI.md`, `AGENTS.md`, `.codex/config.toml`. The current
implementation uses a whole-file ownership model with an `AUTO-GENERATED`
header — it either owns the entire file or skips it. This prevents
co-existence with user-authored content and makes install/uninstall
destructive.

## Considerations

- Industry standard (Ansible `blockinfile`, Salt `blockreplace`,
  Terraform docs) uses comment-based markers for idempotent managed
  sections within user-owned files.

- No AI coding tool currently uses managed blocks in instruction files.
  All treat CLAUDE.md/GEMINI.md/AGENTS.md as 100% user space.

- Markdown renderers handle custom HTML tags as Type 7 blocks (end at
  blank line), but this only affects rendering — AI tools read raw text.

- TOML has a table conflict risk: managed blocks that introduce `[table]`
  headers may conflict with user-defined tables.

- JSON has no comment syntax; managed blocks are not feasible without
  format extension. Current JSON files (.mcp.json) are fully
  vaultspec-owned.

## Decision

### Tag format

Use `<vaultspec type="TYPE">` / `</vaultspec>` as the managed content
delimiter across all supported file formats:

**Markdown files:**

```markdown
<vaultspec type="config">
Managed content here.
</vaultspec>
```

**TOML files:**

```toml

# <vaultspec type="config">

managed_key = "value"

# </vaultspec>

```

### Tag types

| Type     | Purpose                     | Used In                         |
| -------- | --------------------------- | ------------------------------- |
| `config` | Framework + project content | CLAUDE.md, GEMINI.md, AGENTS.md |
| `rules`  | Rule references             | .gemini/GEMINI.md               |
| `agents` | Agent definitions           | .codex/config.toml              |
| `system` | System prompt content       | (reserved for future)           |

### Behavioral contract

| Operation                        | Behavior                                                    |
| -------------------------------- | ----------------------------------------------------------- |
| Install (file absent)            | Create file with managed block only                         |
| Install (file exists, no block)  | Append managed block to end                                 |
| Install (file exists, has block) | Replace content between markers                             |
| Sync                             | Replace managed block content, leave user content untouched |
| Uninstall                        | Strip managed block + markers, preserve user content        |
| Orphaned opening                 | Error — refuse to write, warn user                          |
| Orphaned closing                 | Ignore (stale artifact)                                     |
| Duplicate type in same file      | Error — refuse to write                                     |

### Parsing approach

Line-based string operations. No markdown or TOML parser required for
marker management. The algorithm:

1. Split content into lines
1. Scan for opening tag line
1. Scan forward for matching closing tag
1. Replace, insert, or strip as needed
1. Join lines and return

### TOML robustness

For TOML files, add optional post-write validation using `tomlkit` or
`tomllib` to detect table conflicts. If the resulting file is invalid
TOML, roll back the write and warn the user.

### JSON

Not applicable. `.mcp.json` is fully vaultspec-owned. JSON managed
blocks deferred — if needed, sidecar file pattern recommended.

## Rationale

### Why `<vaultspec>` over HTML comments

HTML comments (`<!-- BEGIN -->`) are invisible in rendered markdown,
which is good for aesthetics but bad for discoverability. Users cannot
see that a section is managed when viewing the rendered file.
`<vaultspec>` tags are semantic, self-documenting, and support `type=`
attributes for multiple blocks without inventing unique comment strings.

### Why `type=` attributes

Multiple managed blocks may coexist in a single file. For example,
`.codex/config.toml` has separate `config` and `agents`
blocks. Attributes avoid the proliferation of unique marker constants
(currently 6 constants for 3 TOML blocks alone).

### Why line-based parsing over AST

All markdown parsers (markdown-it-py, mdformat, marko, mistune) are
one-way markdown→HTML converters. None support round-trip markdown
serialization. Line-based string operations provide perfect round-trip
fidelity with zero dependencies.

### Why not whole-file ownership

The current whole-file model forces users to choose between vaultspec-
managed configuration OR their own content. This is the wrong tradeoff
for files like CLAUDE.md where users have project-specific instructions
that should persist across vaultspec sync operations.

## Rejected alternatives

- **HTML comments (`<!-- BEGIN/END -->`)**:Invisible in rendered output,
  no attribute support, requires unique strings per block type.

- **YAML frontmatter**: Only manages the file header, not body sections.
  Not applicable for TOML files.

- **Full markdown parser (mdformat, marko)**: No round-trip fidelity.
  Would corrupt user formatting.

- **tomlkit for all TOML operations**: Adds dependency for what line-
  based operations handle simply. Reserved for validation only.

## Consequences

- All existing `CONFIG_HEADER`, `CODEX_*_BEGIN/END` constants will be
  replaced by the unified `<vaultspec>` tag system.

- Backward compatibility: first sync after upgrade must detect old
  markers and migrate to new format automatically.

- The tag system is extensible — new `type=` values can be added
  without new marker constants.

- Users can safely add content above, below, or around managed blocks.

- Uninstall becomes non-destructive — user content is preserved.

## Approved decisions (2026-03-16)

1. **Tag attributes:** `type=` only. Additional attributes deferred.

1. **Closing tag:** `</vaultspec>` (simple, no type repetition).

1. **Duplicates:** Error — strict + report mode. One block per type per
   file. On any invalid state (duplicate, orphaned, nested), refuse to
   write and return a structured error with line numbers. Never crash,
   never auto-fix. The CLI logs the error and exits with non-zero code.

1. **tomlkit:** Not added. String-based marker operations only, same
   pattern as markdown. No new dependency.

1. **Codex rules:** No separate adapter needed. Codex behavioral rules
   are delivered via `AGENTS.md` rule references — the same mechanism
   as Claude and Gemini. Codex's `.codex/rules/` system is for
   execution policies (command allow/deny), not coding conventions.

## Error handling contract

| Condition                        | Severity | Action                             |
| -------------------------------- | -------- | ---------------------------------- |
| Duplicate `<vaultspec type="X">` | Error    | Refuse write, report line numbers  |
| Opening without closing          | Error    | Refuse write, report line number   |
| Closing without opening          | Warning  | Ignore orphan, proceed normally    |
| Nested `<vaultspec>` tags        | Error    | Refuse write, report both lines    |
| Tags inside fenced code blocks   | N/A      | Ignored (code fence state machine) |
| File does not exist              | OK       | Create file with managed block     |
| File exists, no block            | OK       | Append managed block to end        |
| File exists, valid block         | OK       | Replace content between markers    |

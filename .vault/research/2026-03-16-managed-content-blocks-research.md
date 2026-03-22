---
tags:
  - '#research'
  - '#install-cmds'
date: '2026-03-16'
related:
  - '[[2026-03-16-binding-decisions]]'
  - '[[2026-03-15-install-cmds-capability-audit]]'
---

# Managed content blocks: research and design

Research into how vaultspec-core should insert, update, and remove
managed content sections within files that may also contain user-authored
content. This is a prerequisite for non-destructive install/uninstall
and safe sync operations.

## Problem statement

vaultspec syncs framework configuration, rule references, and agent
definitions into files like `CLAUDE.md`, `GEMINI.md`, `AGENTS.md`, and
`.codex/config.toml`. These files may also contain user-written content.
The current implementation uses whole-file ownership (`CONFIG_HEADER`
check) which either overwrites the entire file or skips it entirely.
There is no middle ground for co-existence.

## Industry precedents

### Ansible `blockinfile` (gold standard)

- **Markers:** `# {mark} ANSIBLE MANAGED BLOCK` where `{mark}` → BEGIN/END

- **Parsing:** Line-by-line scan. Find BEGIN marker, find END marker,
  replace slice between them.

- **First insert:** Appends to EOF (or uses `insertafter`/`insertbefore`)

- **Removal:** `state: absent` strips the marked block

- **Idempotent:** Same content = no change on second run

- **Corruption guard:** Warns if `{mark}` missing from marker template

- **Source:** https://docs.ansible.com/projects/ansible/latest/collections/ansible/builtin/blockinfile_module.html

### Salt `blockreplace`

- Same marker-based pattern
- `append_if_not_found` / `prepend_if_not_found` for first insertion
- Keeps two copies in memory to detect changes
- **Source:** https://docs.saltproject.io/en/3006/ref/states/all/salt.states.file.html

### Terraform docs generator

- Uses `<!-- BEGIN_TF_DOCS -->` / `<!-- END_TF_DOCS -->` HTML comments
- String-based replacement between markers
- Common in terraform-docs community tool

### gitignore.io

- URL-based comment markers: `# Created by ...` / `# End of ...`
- Preserves user content outside markers

### AI coding tools (Claude, Gemini, Codex, Cursor)

- **None use managed blocks.** All treat config files as 100% user space.

- Claude Code `/init` suggests improvements to existing CLAUDE.md,
  does not overwrite.

- This is an opportunity for vaultspec to pioneer co-existence.

## Proposed tag system: `<vaultspec>`

### Why custom XML tags over HTML comments

| Aspect           | HTML comments `<!-- -->`     | Custom tags `<vaultspec>`    |
| ---------------- | ---------------------------- | ---------------------------- |
| Semantic clarity | Low — comments are invisible | High — explicit tag name     |
| Extensibility    | No attributes                | `type="config"` attributes   |
| Consistency      | Different syntax per format  | Same tag, adapted per format |
| Readability      | Hidden in rendered output    | Visible as tag in source     |
| Multiple blocks  | Need unique comment text     | `type=` differentiates       |

### Format-specific syntax

**Markdown** (`.md` files):

```markdown
<vaultspec type="config">

## Framework Configuration

Content managed by vaultspec.
</vaultspec>
```

**TOML** (`.toml` files):

```toml

# <vaultspec type="config">

model = "gpt-5-codex"

# </vaultspec>

```

**JSON**: Not applicable — `.mcp.json` is fully vaultspec-owned.
If needed in future, use sidecar pattern (separate file).

### Tag types (aligned with ProviderCapability)

| Type     | Used In                         | Content                     |
| -------- | ------------------------------- | --------------------------- |
| `config` | CLAUDE.md, GEMINI.md, AGENTS.md | Framework + project content |
| `rules`  | .gemini/GEMINI.md               | Rule references (Gemini)    |
| `agents` | .codex/config.toml              | Agent definitions           |
| `system` | (future)                        | System prompt content       |

## Robustness analysis

### Markdown files

**CommonMark behavior:** `<vaultspec>` is recognized as a Type 7 HTML
block. Type 7 blocks end at a blank line, meaning content with blank
lines would be split by renderers. However:

- **This does not affect vaultspec.** Vaultspec reads raw file content
  as plain text. It does not use a markdown parser.

- **AI tools read raw content.** Claude Code, Gemini CLI, and Codex
  all read the raw file, not rendered HTML.

- **Rendering is secondary.** The rendered appearance of the managed
  block is irrelevant for the functional purpose.

**Parsing approach:** Line-based string operations.

- Opening: find line matching `<vaultspec type="...">` pattern
- Closing: find `</vaultspec>` line after the opening
- Replace/strip content between markers

**Edge cases:**

- Markers inside fenced code blocks: **medium risk**. A naive regex
  WILL match tags inside code blocks. Mitigation: require tags at
  column 0 (0-3 spaces per CommonMark) and maintain a simple toggle
  for fenced code block boundaries (lines starting with \`\`\` or \~~~).

- Multiple blocks with same type: error — refuse and warn.

- Orphaned opening without closing: error — refuse and warn.

- Orphaned closing without opening: ignore (stale artifact).

**CommonMark interaction (from spec analysis):**

- `<vaultspec>` is recognized as Type 7 HTML block (custom tag)

- Type 7 blocks end at blank line — content with blank lines would
  be split across HTML blocks by renderers

- **Irrelevant for vaultspec:** all AI tools (Claude Code, Gemini CLI,
  Codex) read raw file content, never rendered HTML

- GitHub strips unknown tags from rendered view but raw content
  (API, git clone) is untouched

- Anthropic's own prompt format uses XML tags extensively (`<instructions>`,
  `<context>`, etc.) — well-established precedent in LLM ecosystem

**Attribute format:**

- Standardize on double-quoted attributes: `<vaultspec type="config">`
- Simple regex sufficient: `<vaultspec\s+type="([^"]+)"[^>]*>`
- No extra whitespace normalization needed if we control production

### TOML files

**Critical issue: TOML table conflicts.**

If the managed block introduces `[agents.X]` and the user already has
an `[agents.X]` table with the same role name, the file becomes invalid
TOML. TOML does not allow duplicate table headers. (Note: Codex
behavioral rules are delivered via AGENTS.md, not config.toml — the
table conflict concern applies only to agent definitions.)

**Additional TOML findings (from tomlkit research):**

- `# <vaultspec type="config">` is valid TOML (comments accept any
  printable chars including angle brackets)

- `tomllib` (stdlib) is read-only and discards comments — cannot roundtrip

- `tomlkit` (Poetry project) preserves comments, whitespace, ordering
  and supports full roundtrip editing

- TOML tables are contiguous: keys after `# </vaultspec>` but before the
  next `[table]` header would semantically belong to the managed table

- Multiline strings (`"""..."""`) could theoretically contain marker text
  as a false positive (low practical risk)

**Options:**

1. **String-based operations** (current approach): Treat the file as
   plain text. Find `# <vaultspec type="rules">` and
   `# </vaultspec>`, replace content between. Fast, simple, but
   cannot detect TOML semantic conflicts.

1. **tomlkit** (comment-preserving TOML parser): Parse the full TOML
   AST with comments preserved. Can detect duplicate tables, merge
   settings, and write back without losing user comments or formatting.
   Adds a dependency but is the robust choice.

   - Source: https://github.com/python-poetry/tomlkit
   - Used by Poetry for pyproject.toml manipulation
   - Preserves comments, indentation, ordering

1. **Hybrid**: Use string operations for marker management, tomlkit
   for validation. Parse after writing to verify the file is valid TOML.

**Recommendation:** String-based operations for marker management
(consistent with markdown approach) plus post-write tomlkit validation
to catch table conflicts. Add tomlkit as an optional dependency.

### JSON files

JSON has no comment syntax. Two options:

1. **Sidecar pattern**: vaultspec writes its own file, consuming tool
   merges at load time. This is the Docker Compose override model.

1. **Marker key**: Use a `"__vaultspec"` key as a namespace.

Current state: `.mcp.json` is fully vaultspec-owned. No JSON files
require managed block co-existence. **Defer JSON support.**

## Parsing implementation

### Core functions (format-agnostic)

```python
def find_managed_block(
    content: str,
    block_type: str,
    comment_prefix: str = "",
) -> tuple[int, int] | None:
    """Find the start and end byte offsets of a managed block."""

def upsert_managed_block(
    content: str,
    block_type: str,
    block_content: str,
    comment_prefix: str = "",
) -> str:
    """Insert or replace a managed block in file content."""

def strip_managed_block(
    content: str,
    block_type: str,
    comment_prefix: str = "",
) -> str:
    """Remove a managed block from file content."""

def has_managed_block(
    content: str,
    block_type: str,
    comment_prefix: str = "",
) -> bool:
    """Check whether a managed block exists."""
```

### Format dispatch

| Format   | Opening tag              | Closing tag      | comment_prefix |
| -------- | ------------------------ | ---------------- | -------------- |
| Markdown | `<vaultspec type="X">`   | `</vaultspec>`   | `""` (none)    |
| TOML     | `# <vaultspec type="X">` | `# </vaultspec>` | `"# "`         |

### Algorithm (line-based)

```

1. Split content into lines
2. Scan for opening tag line (prefix + `<vaultspec type="TYPE">`)
3. If found, scan forward for closing tag line (prefix + `</vaultspec>`)
4. If both found: replace lines between them (exclusive of markers)
5. If only opening found: error (orphaned marker)
6. If neither found: append block to end with blank line separator
7. Join lines and return
```

## Migration path from current markers

| Current Marker                                   | New Tag                       |
| ------------------------------------------------ | ----------------------------- |
| `<!-- AUTO-GENERATED by cli.py config sync. -->` | `<vaultspec type="config">`   |
| `# BEGIN VAULTSPEC MANAGED CODEX CONFIG`         | `# <vaultspec type="config">` |
| `# END VAULTSPEC MANAGED CODEX CONFIG`           | `# </vaultspec>`              |
| `# BEGIN VAULTSPEC MANAGED CODEX RULES`          | `# <vaultspec type="rules">`  |
| `# END VAULTSPEC MANAGED CODEX RULES`            | `# </vaultspec>`              |
| `# BEGIN VAULTSPEC MANAGED CODEX AGENTS`         | `# <vaultspec type="agents">` |
| `# END VAULTSPEC MANAGED CODEX AGENTS`           | `# </vaultspec>`              |

**Backward compatibility:** On first sync after upgrade, detect old
markers and migrate to new format automatically.

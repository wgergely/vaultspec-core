---
# ALLOWED TAGS - DO NOT REMOVE
# REFERENCE: #adr #audit #exec #plan #reference #research #mcp-cli-interface
# Directory tag (hardcoded - DO NOT CHANGE - based on .vault/audit/ location)
# Feature tag (replace mcp-cli-interface with your feature name, e.g., #editor-demo)
tags:
  - "#audit"
  - "#mcp-cli-interface"
# ISO date format (e.g., 2026-02-06)
date: "2026-03-21"
# Related documents as quoted wiki-links
# (e.g., "[[2026-02-04-feature-research]]")
related: []
---

<!-- DO NOT add 'Related:', 'tags:', 'date:', or other frontmatter fields
     outside the YAML frontmatter above -->

# `mcp-cli-interface` audit: `mcp-facade-current-state`

## Scope

<!-- What was audited and why -->

## Findings

<!-- Key findings organized by severity -->

## Recommendations

<!-- Actionable recommendations -->


## Context

# `mcp-cli-interface` audit: `current-facade`

## Scope

Document the current MCP tool surface as implemented in
`src/vaultspec_core/mcp_server/vault_tools.py` after the consolidation
that reduced the surface from 7 overloaded tools to 2 focused tools.

This audit supersedes the 7-tool surface described in the 2026-03-17
domain-alignment audit. The redesign proposed there has been partially
realised - the current facade is leaner than even the proposed 15-tool
target, favouring composability over exhaustive CLI parity.

## Current MCP Tool Surface (2 tools)

| # | Tool | Domain | Read/Write | Annotations |
|---|------|--------|------------|-------------|
| 1 | `find` | vault | read-only | `readOnlyHint=True`, `idempotentHint=True`, `openWorldHint=False` |
| 2 | `create` | vault | write | `readOnlyHint=False`, `destructiveHint=False`, `idempotentHint=True`, `openWorldHint=False` |

## `find` - vault document discovery and feature listing

### Modes

1. **Feature listing** (no filters) - returns all features with `name`,
   `doc_count`, and graph `weight` from `VaultGraph.get_feature_rankings`.
   Pass `json=True` to include `status`, `types`, `earliest_date`, `has_plan`.

2. **Document search** (any filter set) - returns documents matching
   `feature`, `type`, and/or `date`. Type defaults to
   `[adr, plan, research, reference]` - exec and audit excluded unless
   explicitly requested. Pass `body=True` to include full document content.

### Parameters

| Param | Type | Default | Notes |
|-------|------|---------|-------|
| `feature` | `str \| None` | `None` | Filter by feature tag |
| `type` | `list[str] \| None` | `None` | Filter by doc type(s); defaults to adr/plan/research/reference |
| `date` | `str \| None` | `None` | Filter by date |
| `body` | `bool` | `False` | Include full document body in results |
| `json` | `bool` | `False` | Include extended fields in feature listing mode |
| `limit` | `int` | `20` | Max results returned |

### Returns

List of dicts. Feature mode: `{name, doc_count, weight}`.
Document mode: `{name, type, feature, date, path[, body]}`.

## `create` - vault document authoring

Scaffolds a new vault document from a type template, replacing
`{feature}`, `{yyyy-mm-dd}`, `{topic}`, and `{title}` placeholders.
Appends a `## Context` section if `content` is provided.

### Parameters

| Param | Type | Default | Notes |
|-------|------|---------|-------|
| `feature` | `str` | required | Feature tag (leading `#` stripped automatically) |
| `type` | `str \| None` | `"research"` | Document type (must match a `DocType` enum value) |
| `date` | `str \| None` | today | ISO date for filename and frontmatter |
| `title` | `str \| None` | feature name | Slug used in filename and template |
| `content` | `str \| None` | `None` | Extra context appended as `## Context` section |

### Behaviour

- Validates type against `DocType` enum
- Loads template from `TEMPLATES_DIR/{type}.md`
- Generates filename: `{date}-{feature}-{type}.md` (exec uses `-exec-{title}` variant)
- Validates filename via `VaultConstants.validate_filename`
- Writes atomically via `atomic_write`; refuses to overwrite existing files
- Returns `{success, path, message}` on success or `{success, message}` on failure

### Guards

- Will not overwrite an existing document (idempotent)
- Will not create documents with invalid types or filenames
- Will not write to missing directories

## Design rationale

The 2-tool surface is intentionally minimal:

- **`find` covers both discovery and introspection** - an agent can list
  features, search documents, and read full bodies through one tool with
  progressive disclosure via `body` and `json` flags.

- **`create` is the only write operation** - all other mutations (edit,
  remove, rename, revert) remain CLI-only, keeping the MCP surface
  non-destructive by design.

- **No spec-domain tools** - rules, skills, agents, and system prompt
  inspection are not exposed. These are framework configuration concerns
  better handled through the CLI or direct file reads.

- **No lifecycle commands** - install, uninstall, and sync remain
  human-initiated through the CLI.

## Assessment

The current 2-tool facade is clean, well-annotated, and fit for purpose.
The `find`/`create` pair provides sufficient capability for agent-driven
vault exploration and document authoring without surface bloat.

### Strengths

- Minimal cognitive load for LLM agents (2 tools vs 7 or 15)
- Clear read/write separation with correct MCP annotations
- Progressive disclosure via optional flags rather than tool proliferation
- Non-destructive by design - no delete, rename, or overwrite paths
- Graph-weight scoring in feature listing provides agentic value

### Gaps to monitor

- No graph export tool (agents cannot inspect cross-feature relationships
  beyond weight scores)
- No feature lifecycle view beyond what `find(json=True)` infers
- `limit=20` default may truncate large vaults silently

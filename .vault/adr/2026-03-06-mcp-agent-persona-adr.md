---
tags:
  - "#adr"
  - "#framework"
date: "2026-03-06"
related:
  - "[[2026-03-06-mcp-agent-persona-research.md]]"
---

# Architecture Decision Record: MCP Agent Persona Tools

## Context
Agents operating within the vaultspec framework need programmatic access to vault documents. They must be able to:
1.  **Read**: Find relevant documents (ADRs, Plans, Research).
2.  **Navigate**: Understand the status of a feature based on existing artifacts.
3.  **Write**: Create new documents following strict templates and conventions.

Currently, agents rely on generic file system tools (`list_directory`, `read_file`, `grep_search`), which lack semantic understanding of the vault structure (tags, frontmatter).

## Decision
We will implement dedicated "Agent Persona" tools within the `vaultspec-mcp` server (`vaultspec.mcp_server.vault_tools`).

### 1. `query_vault`
- **Purpose**: Structured query for vault documents by metadata and content.
- **Parameters**: `query` (text, optional), `type` (optional: `#adr`, `#plan`, etc.), `feature` (optional: `#{feature}`), `related_to` (optional: filter by document relationships), `recent` (optional: return recently modified), `limit` (optional: max results, default 20).
- **Behavior**: Scans all `.md` files in `.vault/`, parses frontmatter to filter by tags and relationships, and performs text search on content.

### 2. `feature_status`
- **Purpose**: Derive the lifecycle stage of a feature.
- **Parameters**: `feature` (feature name).
- **Behavior**: Aggregates all documents sharing the `#{feature}` tag and determines status:
    - `In Progress` (has `#exec`)
    - `Planned` (has `#plan`)
    - `Specified` (has `#adr`)
    - `Researching` (has `#research`)
    - `Unknown` (none)

### 3. `create_vault_document`
- **Purpose**: Create compliant vault documents from templates.
- **Parameters**: `type` (document type), `feature` (feature name), `title` (document title/topic), `extra_context` (optional: additional content to append).
- **Behavior**:
    - Loads the corresponding template from `.vaultspec/rules/templates/`.
    - Injects context variables (`{feature}`, `{yyyy-mm-dd}`, `{title}`).
    - Validates the filename against vault naming conventions.
    - Writes the file to the correct subdirectory.

## Implementation Details
- Tools utilize `vaultspec_core.vaultcore` for parsing and validation.
- Templates are loaded from `vaultspec_core.core.types.TEMPLATES_DIR`.
- Implementation resides in `src/vaultspec_core/mcp_server/vault_tools.py`.
- Tool names were refined during implementation for consistency: `query_vault` (structured query, not just search), `feature_status` (drops redundant `get_` prefix), `create_vault_document` (scoped to vault namespace).

## Consequences
- **Positive**: Agents can reliably interact with the vault without manual file manipulation errors. Enforces consistency.
- **Negative**: Adds maintenance overhead for the MCP server.

## Status
Accepted

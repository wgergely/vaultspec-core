---
tags:
  - "#research"
  - "#framework"
date: "2026-03-06"
related:
  - "[[2026-02-22-mcp-consolidation-adr]]"
---

# Framework research: MCP Agent Persona Tools

Research into implementing "Agent Persona" capabilities within the `vaultspec-mcp` server. The goal is to enable agents to autonomously navigate, query, and extend the vault.

## Findings

### 1. Vault Access Layer
The `vaultspec.vaultcore` package provides all necessary primitives for accessing the vault safely.

- **Scanning**: `vaultspec.vaultcore.scanner.scan_vault(root_dir)` yields all markdown files.
- **Parsing**: `vaultspec.vaultcore.parser.parse_vault_metadata(content)` extracts strict `DocumentMetadata`.
- **Typing**: `vaultspec.vaultcore.models.DocType` and `DocumentMetadata` ensure type safety.
- **Validation**: `VaultConstants.validate_filename` ensures naming conventions.

### 2. Feature Status Logic
We can derive feature status by aggregating documents sharing a common `#{feature}` tag.

| Status | Condition |
| :--- | :--- |
| **In Progress** | `#exec` documents exist. |
| **Planned** | `#plan` document exists (and no `#exec`). |
| **Specified** | `#adr` document exists (and no `#plan`). |
| **Researching** | `#research` document exists (and no `#adr`). |
| **Unknown** | No documents found. |

### 3. Document Creation
Templates are stored in `.vaultspec/rules/templates/` (accessible via `vaultspec.core.types.TEMPLATES_DIR`).

Creation workflow:
1. Load template (e.g., `adr.md`, `plan.md`).
2. Replace placeholders: `{feature}`, `{yyyy-mm-dd}`, `{topic}`, etc.
3. Validate filename using `VaultConstants.validate_filename`.
4. Write atomically using `vaultspec.core.helpers.atomic_write`.

### 4. Search Implementation
A naive search is sufficient for now:
1. Scan all vault files.
2. Parse metadata.
3. Filter by `type` (directory tag) and `feature` (feature tag).
4. Perform case-insensitive string containment check on title/body for `query`.

## Proposed Tools

1. **`search_vault(query: str, type: str | None, feature: str | None)`**
   - Returns: List of `{ path, title, type, feature, score }`.

2. **`get_feature_status(feature: str)`**
   - Returns: `{ feature, status, documents: { research: [], adr: [], ... } }`.

3. **`create_document(type: str, feature: str, title: str, extra_context: str)`**
   - Returns: `{ path, success, message }`.
   - Notes: Needs to handle different template requirements (e.g., research needs `{topic}`).

## Implementation Plan
- Modify `src/vaultspec/mcp_server/vault_tools.py` to import `vaultspec.vaultcore`.
- Implement helper functions for template loading and replacement.
- Register tools with `FastMCP`.

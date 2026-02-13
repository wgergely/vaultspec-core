---
# ALLOWED TAGS - DO NOT REMOVE - REFERENCE: #adr #exec #plan #reference #research #vault-api
# Directory tag (hardcoded - DO NOT CHANGE - based on .vault/adr/ location)
# Feature tag (replace vault-api with your feature name, e.g., #editor-demo)
tags:
  - "#plan"
  - "#vault-api"
# ISO date format (e.g., 2026-02-06)
date: 2026-02-08
# Related documents as quoted wiki-links (e.g., "[[2026-02-04-feature-research]]")
related:
  - "[[2026-02-08-vault-api-adr]]"
---
<!-- DO NOT add 'Related:', 'tags:', 'date:', or other frontmatter fields outside the YAML frontmatter above -->

# vault-api plan: Implementation of Docs Verification and Scaffolding

## Goal

Formalize the markdown rule system into a Python backend API and provide a unified CLI tool (`docs.py`) for auditing and managing the `.vault/` universe.

## Phase 1: Core API and Auditing (Completed)

- [x] **Modular Structure**: Implement `vault`, `verification`, `graph`, and `metrics` modules.
- [x] **Frontmatter Parsing**: Implement robust YAML extraction and validation.
- [x] **Connectivity Analysis**: Build Graph API to find hotspots, orphans, and invalid links.
- [x] **Reporting CLI**: Implement `docs.py audit` with `--summary`, `--verify`, and `--graph`.
- [x] **JSON Output**: Add `--json` flag for machine readability.

## Phase 2: Write API and Scaffolding (Completed)

- [x] **Template Logic**: Implement hydration system for `.vaultspec/templates/`.
- [x] **Doc Scaffolding**: Implement `docs.py create` to generate compliant files with correct naming and metadata.

## Phase 3: Vertical Integrity (Pending)

- [ ] **Cross-Type Validation**: Ensure every `#feature` has a master `/plan`.
- [ ] **Execution Mapping**: Verify `exec` records link back to specific phases in their parent `plan`.
- [ ] **Body Schema**: Validate Markdown headers against templates (e.g., ADRs must have "Consequences").

## Phase 4: MCP and Advanced Analysis (Future)

- [ ] **Docs-MCP**: Wrap the API into a Model Context Protocol server.
- [ ] **Auto-Healing**: Implement suggestions for fixing broken wiki-links.
- [ ] **Semantic Bridge**: Integrate vector-based RAG for meaning-aware document lookup.

## Status Summary

Phase 1 and 2 are fully implemented. The system successfully audited the `mock-project` and is ready for production use in the main workspace.

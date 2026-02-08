---
# ALLOWED TAGS - DO NOT REMOVE - REFERENCE: #adr #exec #plan #reference #research #vault-rag
# Directory tag (hardcoded - DO NOT CHANGE - based on .docs/adr/ location)
# Feature tag (replace vault-api with your feature name, e.g., #editor-demo)
tags:
  - "#plan"
  - "#vault-rag"
# ISO date format (e.g., 2026-02-06)
date: 2026-02-08
# Related documents as quoted wiki-links (e.g., "[[2026-02-04-feature-research]]")
related:
  - "[[2026-02-08-vault-rag-adr]]"
---
<!-- DO NOT add 'Related:', 'tags:', 'date:', or other frontmatter fields outside the YAML frontmatter above -->

# vault-rag plan: Bootstrapping Vault Knowledge with Semantic Search

## Goal

Implement a lightweight semantic search system for the `.docs/` vault to enable meaning-based document discovery and bootstrapping of agent knowledge.

## Phase 1: Search Engine (In Progress)

- [ ] **`vault/rag.py`**: Implement the core search logic using document signatures.
- [ ] **Indexing Engine**: Logic to generate and cache "Semantic Signatures" for all docs.
- [ ] **Ranking Logic**: Pure-Python TF-IDF pre-filter followed by LLM-based ranking.

## Phase 2: CLI Integration

- [ ] **`docs.py index`**: Command to scan and build/update the semantic index.
- [ ] **`docs.py search`**: Command to perform queries and return ranked results with snippets.

## Phase 3: Agent Tooling

- [ ] **Bootstrap Tool**: A tool for agents to "Search Vault" when starting a new task.
- [ ] **Creation Suggestions**: Integrate search into `docs create` to automatically suggest "Related" documents.

## Phase 4: Maintenance

- [ ] **Auto-update**: Trigger incremental indexing on file changes.
- [ ] **Integrity**: Ensure the index is always in sync with the file system.

## Status Summary

Proposed and planning initiated. The design avoids heavy vector database dependencies in favor of a lightweight LLM-assisted search pattern.

---
tags:
  - '#adr'
  - '#vault-api'
date: '2026-02-08'
related:
  - '[[2026-02-08-vault-api-plan]]'
---

<!-- DO NOT add 'Related:', 'tags:', 'date:', or other frontmatter fields outside the YAML frontmatter above -->

# vault-api adr: Modular Docs API and Auditing System | (**status:** accepted)

## Problem Statement

The `.vault/` universe was governed by rigid markdown rules (Rule of Two for tags, specific naming patterns, mandatory frontmatter) that were only partially enforced via brittle scripts. There was no centralized API to programmatically interact with, verify, or analyze the connectivity of these documents, making it difficult for agents to maintain vault integrity.

## Considerations

- **Modularity:** The system needs to separate parsing, scanning, verification, and graph analysis to keep the backend maintainable.
- **Connectivity Analysis:** Identifying hotspots (most referenced) and orphans is critical for vault health.
- **Machine Interface:** The system must be ready for future MCP (Model Context Protocol) integration via JSON outputs.
- **Scaffolding:** Agents need a way to create compliant documents without manual boilerplate management.

## Constraints

- Must be pure Python without heavy external dependencies.
- Must strictly adhere to the existing `.vault/` folder structure and naming conventions.
- Must support both human-readable CLI output and machine-readable JSON.

## Implementation

The system is implemented as a modular suite under `.vaultspec/lib/src/`:

- **`vault/`**: Core primitives for scanning, parsing frontmatter, and extracting links.
- **`verification/`**: Rule enforcement logic (`get_malformed`, `verify_file`).
- **`graph/`**: Static connectivity analysis using a directed graph model.
- **`metrics/`**: Summary statistics.
- **`vault.py`**: A unified CLI entry point supporting `audit` and `create` subcommands.

## Rationale

Decoupling the graph and verification APIs from the core parser allows us to build complex analysis tools (like feature ranking) without bloating the file-handling logic. Using standard library `argparse` and `json` ensures the tool is lightweight and portable across environments.

## Consequences

- **Formalized Standards:** The rigid rules are now enforced by code, not just convention.
- **Agent Productivity:** Agents can now use `docs create` to instantly generate compliant documents.
- **MCP Readiness:** The JSON output flag provides a stable interface for a future MCP server.
- **Future Growth:** The modular structure allows for future expansion into semantic search (RAG) and auto-healing of broken links.

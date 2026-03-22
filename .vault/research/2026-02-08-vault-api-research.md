---
tags:
  - '#research'
  - '#vault-api'
date: '2026-02-08'
related:
  - '[[2026-02-08-vault-api-adr]]'
---

# vault-api research

Investigation into modular document API and auditing patterns for the `.vault/` knowledge base.

## Findings

- The `.vault/` universe relies on rigid markdown rules (Rule of Two for tags, naming patterns, mandatory frontmatter) that were only partially enforced via ad-hoc scripts.
- No centralized API existed to programmatically interact with, verify, or analyze document connectivity.
- Agent workflows needed a way to scaffold compliant documents without manual boilerplate management.

## Analysis

- **Modularity requirement**: Parsing, scanning, verification, and graph analysis must be separated to keep the backend maintainable.
- **Connectivity analysis**: Identifying hotspots (most referenced) and orphans is critical for vault health monitoring.
- **Machine interface**: Future MCP integration requires JSON-serializable outputs from all analysis operations.
- **Scaffolding**: A `create` subcommand can generate compliant documents from templates, reducing agent error rates.

## Constraints Identified

- Must be pure Python without heavy external dependencies to keep the tool portable.
- Must strictly adhere to existing `.vault/` folder structure and naming conventions.
- Must support both human-readable CLI output and machine-readable JSON for MCP readiness.

## Recommendation

Implement a modular suite under `.vaultspec/lib/src/` with separated `vault/`, `verification/`, `graph/`, and `metrics/` packages, unified behind a single CLI entry point (`vault.py`) supporting `audit` and `create` subcommands.

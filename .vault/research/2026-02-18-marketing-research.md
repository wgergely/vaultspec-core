---
tags:
  - '#research'
  - '#marketing-audit'
date: '2026-02-18'
related:
  - '[[2026-02-18-marketing-audit-competitor-landscape-research]]'
  - '[[2026-02-18-marketing-audit-documentation-quality-research]]'
  - '[[2026-02-18-marketing-audit-governance-positioning-research]]'
  - '[[2026-02-18-marketing-audit-marketing-assessment-research]]'
  - '[[2026-02-18-marketing-audit-packaging-distribution-research]]'
  - '[[2026-02-18-marketing-audit-positioning-usp-research]]'
  - '[[2026-02-18-marketing-audit-protocol-landscape-research]]'
---

## Marketing Audit: Feature Comparison Table

Feature comparison of vaultspec against leading AI coding tools.
Data sourced from \[[2026-02-18-marketing-audit-competitor-landscape]\].

## Feature Comparison

| Feature                         | vaultspec |  Cursor  |      Aider       | Devin | Windsurf | Claude Code |
| :------------------------------ | :-------: | :------: | :--------------: | :---: | :------: | :---------: |
| Governance Pipeline (R→S→P→E→V) |    Yes    |    No    |        No        |  No   |    No    |     No      |
| Audit Trail (.vault/)           |    Yes    |    No    | Git history only |  No   |    No    |     No      |
| ADR Support                     |    Yes    |    No    |        No        |  No   |    No    |     No      |
| Multi-Protocol (MCP+ACP+A2A)    |    Yes    | MCP only |        No        |  No   |    No    |  MCP only   |
| GPU-Accelerated RAG             |    Yes    |    No    |        No        |  No   |    No    |     No      |
| Open Source                     |    Yes    |    No    |       Yes        |  No   |    No    |     No      |
| Self-Hosted                     |    Yes    |    No    |       Yes        |  No   |    No    |     No      |

## Notes

- **Cursor**: Proprietary VSCode fork. MCP support in agent mode. No governance or audit features.
- **Aider**: MIT-licensed terminal CLI. Git auto-commits provide partial traceability; no spec-driven pipeline or ADR support.
- **Devin**: Closed-source, enterprise-priced autonomous agent. Multi-agent collaboration in Devin 2.0. No governance transparency.
- **Windsurf**: Proprietary IDE with Cascade agentic system. No audit trail or decision documentation.
- **Claude Code**: Proprietary CLI backed by Anthropic API. Agent Skills provide structured capability bundles; no built-in decision audit trail or ADR workflow.
- **vaultspec**: Only tool in this comparison with a full spec-driven governance pipeline, structured ADR documentation, and a persistent `.vault/` audit trail.

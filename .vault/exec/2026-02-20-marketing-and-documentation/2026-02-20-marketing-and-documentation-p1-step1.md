---
tags:
  - "#exec"
  - "#marketing-and-documentation"
date: 2026-02-20
related:
  - "[[2026-02-20-marketing-and-documentation-p1-plan]]"
---

# `marketing-and-documentation` `phase1` `step1`

Created `.vaultspec/docs/` with three sub-chapter files.

- Created: `.vaultspec/docs/concepts.md`
- Created: `.vaultspec/docs/cli-reference.md`
- Created: `.vaultspec/docs/search-guide.md`

## Description

**concepts.md** (~6KB): Tutorial-first structure. Section 1 merges all content from
`docs/tutorials/first-governed-feature.md` — the `/health` endpoint worked example with
sample artifact output at each phase and the final `.vault/` directory tree. Section 2
merges all content from `docs/concepts.md` — SDD definition, governance mechanisms,
`.vault/` knowledge base table, agents/skills/rules, protocol stack, and Mermaid diagrams.
Redundant 5-phase overview tables were consolidated rather than duplicated.

**cli-reference.md** (~14KB): All content from `docs/cli-reference.md` (cli.py, docs.py,
subagent.py with flags and examples) followed by a `## Configuration Reference` appendix
consolidating all content from `docs/configuration.md`. Variables restructured into a
single table per category (Agent, MCP Server, A2A, Storage, Tool Directory, RAG,
Orchestration, I/O, Editor) with Var/Type/Default/Description columns.

**search-guide.md** (~3KB): All content from `docs/search-guide.md` minus the trailing
`## Configuration` table (which is now in `cli-reference.md`). Replaced with a single
cross-reference line pointing to `cli-reference.md#configuration-reference`.

## Tests

Content completeness verified by inspection:
- `concepts.md` contains "health_handler" (tutorial content present)
- `cli-reference.md` contains "VAULTSPEC_ROOT_DIR" (configuration appendix present)
- `search-guide.md` does NOT contain "VAULTSPEC_EMBEDDING_MODEL" (config table removed)

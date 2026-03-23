---
tags:
  - '#exec'
  - '#marketing-and-documentation'
date: '2026-02-20'
related:
  - '[[2026-02-20-marketing-and-documentation-p1-plan]]'
---

# `marketing-and-documentation` `phase1` summary

Restructured all documentation from a root-level `docs/` tree into three
deployed sub-chapters under `.vaultspec/docs/`, retired twelve source files,
and updated both READMEs to reflect the new structure.

- Created: `.vaultspec/docs/concepts.md`
- Created: `.vaultspec/docs/cli-reference.md`
- Created: `.vaultspec/docs/search-guide.md`
- Modified: `README.md`
- Modified: `.vaultspec/README.md`
- Deleted: `docs/` directory tree (12 files across 4 subdirectories)

## Description

The `docs/` folder at the repository root is not deployed with the vaultspec
framework in production. All operational documentation was moved to
`.vaultspec/docs/`, which travels with the framework.

**Step 1 (Phase 2 in plan order):** Created three sub-chapters under
`.vaultspec/docs/`:

- `concepts.md` — tutorial-first (worked `/health` endpoint example with sample
  artifact output at each phase) followed by the SDD methodology reference,
  agents/skills/rules explanation, protocol stack, and Mermaid diagrams.
  Sourced from `docs/tutorials/first-governed-feature.md` + `docs/concepts.md`.

- `cli-reference.md` — all three CLIs (`cli.py`, `vault.py`, `subagent.py`)
  plus a `## Configuration Reference` appendix consolidating all
  `VAULTSPEC_*` env vars. Sourced from `docs/cli-reference.md` +
  `docs/configuration.md`.

- `search-guide.md` — hybrid retrieval pipeline, filter syntax, GPU
  requirements, incremental indexing, and performance data. Config table
  removed; replaced with a link to `cli-reference.md#configuration-reference`.
  Sourced from `docs/search-guide.md`.

**Step 2 (Phase 1 in plan order):** Deleted all 12 retired files:
`docs/api.md`, `docs/getting-started.md`, `docs/configuration.md`,
`docs/search-guide.md`, `docs/cli-reference.md`, `docs/concepts.md`,
`docs/tutorials/first-governed-feature.md`, `docs/blog/spec-driven-development.md`,
`docs/blog/why-governance.md`, `docs/guides/enterprise-evaluator.md`,
`docs/guides/individual-developer.md`, `docs/guides/team-lead.md`.
Removed `docs/tutorials/`, `docs/blog/`, `docs/guides/`, `docs/`.

**Step 3 (Phase 3 in plan order):** Three targeted edits to `README.md`:

- Added `cli.py doctor` as first post-install verification command.

- Added `## Worked Example` section showing 5 skill invocations and artifact
  paths, with link to `concepts.md` for the full tutorial.

- Updated Documentation links from `docs/*.md` to `.vaultspec/docs/*.md`;
  collapsed four links to three (getting-started retired; configuration folded
  into cli-reference).

**Step 4 (Phase 4 in plan order):** Added `## Documentation` navigation
section to `.vaultspec/README.md` linking to the three sub-chapters with
one-line descriptions. No existing content modified.

## Tests

Code review (`2026-02-20-marketing-and-documentation-p1-review`) passed
after two minor revisions:

- `README.md` Project Structure block updated: `docs/` entry replaced with
  `.vaultspec/docs/` to reflect the deleted directory.

- `concepts.md` sample plan task replaced: stale `docs/api.md` reference
  replaced with `tests/test_health_integration.py`.

No CRITICAL or HIGH issues found. All internal links verified valid. All
plan intent decisions confirmed implemented.

**Safety:** Pure documentation change. No executable code introduced.
No crash risk, no security surface change.

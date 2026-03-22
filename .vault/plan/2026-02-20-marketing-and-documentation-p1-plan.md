---
tags:
  - '#plan'
  - '#marketing-and-documentation'
date: '2026-02-20'
related:
  - '[[2026-02-20-marketing-and-documentation-research]]'
  - '[[2026-02-20-marketing-and-documentation-adr]]'
---

# `marketing-and-documentation` `phase1` plan

Restructure and simplify the documentation corpus. The root `docs/` folder is eliminated.
All operational documentation moves to `.vaultspec/docs/` so it deploys with the framework.
Marketing and persona content is retired. The root `README.md` is expanded to absorb the
install/setup flow and an abbreviated 5-phase worked example. `.vaultspec/README.md` becomes
the authoritative overview linking to three sub-chapter files.

## Proposed Changes

Per \[[2026-02-20-marketing-and-documentation-research]\] and the interactive document review:

- **Retire** 9 files: `docs/api.md`, `docs/getting-started.md`, `docs/configuration.md`,
  `docs/tutorials/first-governed-feature.md`, `docs/blog/spec-driven-development.md`,
  `docs/blog/why-governance.md`, `docs/guides/enterprise-evaluator.md`,
  `docs/guides/individual-developer.md`, `docs/guides/team-lead.md`

- **Create** `.vaultspec/docs/` with 3 sub-chapter files

- **Rewrite** `README.md` (root): absorb install steps + abbreviated 5-phase example

- **Update** `.vaultspec/README.md`: trim to overview, add links to `.vaultspec/docs/`

## Tasks

- `Phase 1: Retire`

  1. Delete all 9 retired files listed above. Delete the now-empty `docs/blog/`,
     `docs/guides/`, and `docs/tutorials/` subdirectories. Delete `docs/` itself once
     the 3 surviving source files have been consumed in Phase 2.
     **Agent**: `vaultspec-simple-executor`

- `Phase 2: Create .vaultspec/docs/`

  1. Create `concepts.md`. Structure: **tutorial first, concepts second**.

     - Section 1 (Tutorial): Merge all content from `docs/tutorials/first-governed-feature.md`
       — setup, the 5 phases with `/health` endpoint example, full sample artifact output at
       each phase, the final `.vault/` directory tree. Keep verbatim; this is the best content.

     - Section 2 (Concepts): Merge all content from `docs/concepts.md` — SDD definition,
       governance mechanisms, .vault/ knowledge base table, agents/skills/rules, protocol
       stack, Mermaid diagrams.

     - Destination: `.vaultspec/docs/concepts.md`
       **Agent**: `vaultspec-standard-executor`

  1. Create `cli-reference.md`. Structure: existing CLI reference + configuration appendix.

     - Part 1: All content from `docs/cli-reference.md` verbatim (cli.py, vault.py, subagent.py).

     - Part 2: Append all content from `docs/configuration.md` as a new `## Configuration Reference` appendix section at the end of the file.

     - Destination: `.vaultspec/docs/cli-reference.md`
       **Agent**: `vaultspec-simple-executor`

  1. Create `search-guide.md`. Structure: existing search guide minus the configuration table.

     - Copy all content from `docs/search-guide.md`.

     - Remove the `## Configuration` section at the bottom (the table of VAULTSPEC\_\* vars).
       Replace with a one-line pointer: "See the CLI Reference for the full configuration
       variable list."

     - Destination: `.vaultspec/docs/search-guide.md`
       **Agent**: `vaultspec-simple-executor`

- `Phase 3: Rewrite README.md`

  1. Rewrite the root `README.md`. Keep the existing structure and tone; expand it with:
     - **Quick Start expansion**: The current 3-command block is sufficient for install.
       Extend it to include: (a) `cli.py doctor` as the verification step after install,
       (b) the no-GPU escape hatch note.

     - **5-phase worked example**: Add a new section after "The Workflow" block showing an
       abbreviated version of the `/health` endpoint example from the retired tutorial.
       Show only the 5 skill invocations and the resulting artifact paths — no sample artifact
       content. This is enough to demonstrate the pipeline is concrete without bloating README.

     - **Updated documentation links**: Replace `docs/*.md` links with
       `.vaultspec/docs/*.md` links for concepts, cli-reference, and search-guide.
       Link to the Framework Manual (`.vaultspec/README.md`) as before.
       **Agent**: `vaultspec-standard-executor`

- `Phase 4: Update .vaultspec/README.md`

  1. Add a `## Documentation` section near the top of `.vaultspec/README.md` (after the
     existing overview/introduction content) linking to the three sub-chapters:

     - `[Concepts & Tutorial](.vaultspec/docs/concepts.md)` — SDD methodology, worked example
     - `[CLI Reference](.vaultspec/docs/cli-reference.md)` — all commands + configuration
     - `[Search Guide](.vaultspec/docs/search-guide.md)` — RAG search, GPU requirements

  1. Do not otherwise alter `.vaultspec/README.md` content. The overview, agent table,
     workflow diagrams, and file responsibility tables stay as-is.
     **Agent**: `vaultspec-simple-executor`

## Parallelization

Phase 1 (retire) must complete first — Phase 2 reads the source files before deleting them,
so the retire step must happen after Phase 2 consumes the sources.

Correct order:

1. Phase 2 (create .vaultspec/docs/) — reads source files and creates output
1. Phase 1 (retire) — deletes source files after Phase 2 is complete
1. Phase 3 and Phase 4 — fully independent; run in parallel

Steps 2.1, 2.2, and 2.3 within Phase 2 are independent and can run in parallel.

## Verification

**File system check**: After execution, verify:

- `docs/` directory no longer exists at the repo root
- `.vaultspec/docs/` contains exactly: `concepts.md`, `cli-reference.md`, `search-guide.md`
- No broken links in `README.md` or `.vaultspec/README.md` (all links point to files that exist)

**Content completeness check**:

- `concepts.md` contains the `/health` endpoint tutorial content (search for "health_handler")
- `cli-reference.md` contains the configuration table (search for "VAULTSPEC_ROOT_DIR")
- `search-guide.md` does NOT contain the configuration table (search for "VAULTSPEC_EMBEDDING_MODEL" — should not appear)

**Link audit**: Run `vault.py audit --verify` after completion to confirm no broken wiki-links
were introduced. The vault's internal `.vault/` links are unaffected by this change (they do
not reference `docs/` files).

**Honest note**: Content quality is subjective. The plan specifies where content goes and
what is trimmed, but the agent should exercise judgment when merging sections — headings may
need renaming to avoid duplication, and redundant paragraphs between the tutorial and concepts
sections of `concepts.md` should be removed rather than preserved verbatim.

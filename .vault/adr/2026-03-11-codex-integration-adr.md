---
tags:
  - '#adr'
  - '#codex-integration'
date: '2026-03-11'
related:
  - '[[2026-03-11-codex-integration-research]]'
  - '[[2026-02-22-cli-ecosystem-factoring-adr]]'
---

<!-- DO NOT add 'Related:', 'tags:', 'date:', or other frontmatter fields
     outside the YAML frontmatter above -->

# `codex-integration` adr: native codex destination model and antigravity normalization | (**status:** `accepted`)

## Problem Statement

vaultspec's current provider model is built around Claude and Gemini:

- per-rule markdown files written into a `rules_dir`
- a generated markdown `config_file` that includes `@rules/...` references
- optional `system_file`
- directory-per-skill outputs under a provider-owned folder

The research in \[[2026-03-11-codex-integration-research]\] shows that Codex and
Antigravity do not fit this model cleanly.

- Codex uses `AGENTS.md` for project instructions, `.agents/skills/` for
  skills, and `.codex/config.toml` for TOML configuration.

- Antigravity's current official workspace layout is `.agents/` with
  `GEMINI.md` still documented for top-level instructions.

- The current CLI still models Antigravity as `.agent` + `AGENTS.md` + an
  `agents` subfolder.

If vaultspec adds Codex on top of this stale Antigravity model, the provider
matrix will encode conflicting assumptions about `.agent` versus `.agents`,
markdown config generation, and destination-owned folder structures.

## Considerations

- Codex natively consumes `AGENTS.md`; it does not document a `CODEX.md` or a
  `.codex/rules/` directory.

- Codex skills live under `.agents/skills/`, outside `.codex/`, which breaks
  the current assumption that `skills_dir` is nested inside a provider folder.

- Codex agent definitions are TOML `[agents.*]` tables, not markdown files in
  an `agents_dir`.

- Antigravity currently documents `.agents/rules/`, `.agents/workflows/`, and
  `.agents/skills/`, while still using `GEMINI.md` for top-level instructions.

- The current resource model has no first-class `workflows` resource.

- The current sync pipeline is transform-based, not raw file copy. Any Codex
  rollout has to be compatible with `transform_rule()`, `_generate_config()`,
  `transform_skill()`, and current system prompt materialization behavior.

## Constraints

- This ADR governs destination modeling only. It does not authorize immediate
  CLI changes.

- The user has asked for research first; implementation requires a later plan.

- vaultspec must not invent unsupported provider conventions such as
  `CODEX.md`, `.codex/rules/`, or a user-managed Antigravity `.agents/agents/`
  folder without primary-source evidence.

- Any Codex support beyond `AGENTS.md` may require new infrastructure for TOML
  mutation and for syncing resources outside a provider-owned root folder.

## Implementation

vaultspec will treat Codex as a **native non-Claude/Gemini destination** rather
than forcing it into the existing markdown-config provider shape.

The implementation direction is:

1. Keep `AGENTS.md` as the immediate Codex instruction bridge because Codex
   already consumes it natively.

1. Do not introduce a fake `CODEX.md` or `.codex/rules/` abstraction.

1. Treat `.agents/skills/` as the correct future target if Codex skills are
   later synchronized.

1. Treat `.codex/config.toml` mutation as a separate explicit capability,
   rather than assuming it falls out of the current `_generate_config()` path.

1. Normalize Antigravity to the officially documented `.agents` workspace
   layout and `GEMINI.md` instruction model before adding Codex as a first-
   class destination.

1. Defer decisions about Antigravity workflows and Codex TOML mutation to the
   planning phase, where they can be scoped as explicit work items.

## Rationale

This decision follows directly from \[[2026-03-11-codex-integration-research]\].

- Codex's closest native fit in vaultspec today is `AGENTS.md`, not the
  `rules_dir` + generated markdown config pipeline.

- Modeling Codex as if it were Claude or Gemini would create unsupported
  artifacts and hide real architectural work behind a misleading provider enum.

- Codex skills and agents require different primitives from the current model:
  `.agents/skills/` for skills and TOML tables for agents.

- Antigravity is already mis-modeled locally. Correcting it first reduces
  ambiguity, prevents `.agent` and `.agents` from coexisting as competing
  truths, and gives Codex a cleaner baseline for comparison.

- Treating destination differences explicitly preserves the integrity of the
  sync engine rather than accreting special cases under false abstractions.

Rejected alternatives:

- Model Codex as a standard markdown-config provider with `CODEX.md` and
  `.codex/rules/`.

- Add `Tool.CODEX` immediately without first deciding whether TOML mutation and
  `.agents/skills/` sync are in scope.

- Preserve the current Antigravity `.agent` + `AGENTS.md` model for backward
  compatibility and add Codex alongside it.

## Consequences

- `AGENTS.md` remains the only clearly supported Codex bridge under the current
  architecture.

- A future Codex implementation will likely need new abstractions for:

  - syncing skills to `.agents/skills/`
  - optionally mutating `.codex/config.toml`
  - representing provider capabilities that do not map to `rules_dir` and
    markdown `config_file`

- Antigravity should be corrected in enums, tool configuration, and scaffolding
  before Codex rollout work begins.

- A later plan must decide whether to add a `workflows` resource for
  Antigravity and whether Antigravity rule files should preserve or change the
  current YAML frontmatter convention.

- This ADR intentionally separates architectural direction from implementation
  sequencing so the next phase can produce a concrete approved plan.

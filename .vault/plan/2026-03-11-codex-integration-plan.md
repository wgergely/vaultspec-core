---
tags:
  - "#plan"
  - "#codex-integration"
date: "2026-03-11"
related:
  - "[[2026-03-11-codex-integration-adr]]"
  - "[[2026-03-11-codex-integration-research]]"
---

<!-- DO NOT add 'Related:', 'tags:', 'date:', or other frontmatter fields
     outside the YAML frontmatter above -->

# `codex-integration` implementation plan

Implement the provider-model changes approved in
[[2026-03-11-codex-integration-adr]] using the destination compatibility
findings in [[2026-03-11-codex-integration-research]]. The work must first
correct Antigravity to current documented conventions, then introduce a Codex
model that uses native destinations instead of forcing Codex into the existing
Claude/Gemini markdown-config abstraction.

## Proposed Changes

The implementation should proceed in four phases.

First, normalize Antigravity so the codebase stops assuming the stale
`.agent` + `AGENTS.md` + `agents/` model. This includes configuration defaults,
provider destination paths, and workspace scaffolding.

Second, refactor the sync destination model where necessary so vaultspec can
represent mixed provider layouts. The current `ToolConfig` and config
generation flow assume a single provider-owned root directory with a markdown
config file and optional rules/system directories. The plan should evolve that
model only as far as needed to support the approved destination shapes:

- Antigravity: `GEMINI.md` plus `.agents/rules`, `.agents/workflows`,
  `.agents/skills`
- Codex: `AGENTS.md`, optional `.codex/config.toml`, and `.agents/skills`

Third, introduce Codex-native sync support. The initial implementation should
prioritize the supported instruction bridge (`AGENTS.md`) and Codex-compatible
skill destinations. TOML-aware Codex config support should be treated as an
explicit scoped task, not an accidental byproduct of markdown config sync.

Fourth, expand the test surface so destination-specific behavior is covered in
collection, transform, sync, and scaffolding paths. Verification should cover
generated artifacts in temporary workspaces, not only isolated transform
functions.

Scope boundary for this plan:

- destination sync and scaffolding are in scope
- protocol execution providers under `src/vaultspec_core/protocol/providers/`
  are out of scope for this rollout unless separately planned

## Tasks

- Phase 1: Normalize Antigravity destination modeling
    1. Update provider enums and configuration defaults so Antigravity resolves
       to the documented `.agents` workspace layout instead of `.agent`.
    2. Correct Antigravity `ToolConfig` assembly in
       `src/vaultspec_core/core/types.py` so its top-level instruction target is
       `GEMINI.md`, not `AGENTS.md`.
    3. Update `src/vaultspec_core/core/commands.py` scaffolding so `init_run()`
       creates the documented Antigravity folders (`rules`, `workflows`,
       `skills`) and stops creating an undocumented `agents` folder.
    4. Audit any tests and fixtures that currently encode `.agent` or
       `AGENTS.md` for Antigravity and rewrite them to the normalized model.

- Phase 2: Decouple destination-path assumptions from a single provider root
    1. Refine the destination configuration model in
       `src/vaultspec_core/core/types.py` so a provider can own a config file in
       one location while syncing skills or other resources elsewhere.
    2. Rework the relevant sync and config-generation paths in
       `src/vaultspec_core/core/config_gen.py`,
       `src/vaultspec_core/core/system.py`, `src/vaultspec_core/core/skills.py`,
       and `src/vaultspec_core/core/sync.py` so provider capabilities are
       explicit instead of inferred from a single root directory.
    3. Decide and encode how root `AGENTS.md` sync, markdown config generation,
       and system-prompt generation coexist without overloading `Tool.AGENTS`
       and `Resource.AGENTS`.
    4. Define the minimum resource-model changes needed for Antigravity
       workflows and Codex-native configuration surfaces without overexpanding
       scope.

- Phase 3: Add Codex-native support
    1. Add Codex as a first-class destination only after the destination model
       can express `.codex/config.toml`, root `AGENTS.md`, and `.agents/skills`
       without fake `CODEX.md` or `.codex/rules` constructs.
    2. Implement Codex instruction support around the existing `AGENTS.md`
       bridge and ensure it composes cleanly with current AGENTS sync behavior.
    3. Reuse skill sync where possible, but retarget Codex skills to
       `.agents/skills/<skill>/SKILL.md` and verify the resulting layout matches
       Codex expectations.
    4. Scope Codex TOML integration explicitly: either implement a safe
       `.codex/config.toml` mutation path now or leave it out of the first
       rollout behind a clear boundary in code and tests.
    5. Confirm that Codex does not participate in markdown config generation,
       rules-directory sync, or system-file fallback unless a native Codex
       counterpart is deliberately added.

- Phase 4: Verification and regression coverage
    1. Expand
       `src/vaultspec_core/tests/cli/test_sync_collect.py`,
       `src/vaultspec_core/tests/cli/test_sync_operations.py`, and
       `src/vaultspec_core/tests/cli/test_sync_incremental.py` to cover the new
       Antigravity and Codex destination shapes.
    2. Add targeted tests for path/config assembly in
       `src/vaultspec_core/core/types.py` and `src/vaultspec_core/core/config_gen.py`
       so mixed-location destinations are exercised directly.
    3. Add scaffolding coverage for `init_run()` to verify `.agents/*`
       creation for Antigravity and whatever Codex scaffolding scope is
       approved. This should include the CLI-facing coverage under
       `src/vaultspec_core/tests/cli/test_spec_cli.py`.
    4. Add end-to-end dry-run or temp-workspace sync checks that validate the
       actual on-disk outputs for Claude, Gemini, Antigravity, and Codex side
       by side.
    5. Update any user-facing documentation touched by the rollout so provider
       conventions and generated destinations stay aligned with the code.

## Parallelization

Phase 1 and Phase 4 test-fixture preparation can start in parallel once the
target Antigravity model is fixed. Within Phase 2, destination-model refactoring
and resource-taxonomy/test design can proceed in parallel if one owner keeps the
canonical contract for `ToolConfig` and sync capabilities. Phase 3 should begin
only after the destination model from Phase 2 is stable; otherwise Codex work
will hard-code transitional assumptions. Documentation updates can run in
parallel with late-stage verification once the final destination behavior is
settled.

## Verification

Mission success means vaultspec can represent and sync the approved provider
destinations without relying on stale `.agent` assumptions or invented Codex
artifacts.

Verification should include:

- unit coverage for destination/path assembly and provider capability decisions
- sync tests that assert correct Antigravity outputs under `.agents/*` and
  correct Codex outputs for `AGENTS.md` and `.agents/skills/*`
- explicit negative coverage showing Codex does not generate unsupported
  markdown config or rules-directory outputs
- scaffolding tests for `init_run()` so the created workspace layout matches the
  approved provider model
- temp-workspace or dry-run validation that generated files land in the right
  places and remain compatible with existing Claude/Gemini behavior
- documentation review to ensure operator guidance matches the implemented
  provider conventions

Beyond unit testing, verification should include inspecting the generated
workspace tree in a temporary project and comparing it against the researched
provider expectations. This guards against passing tests that only validate
internal transforms while still producing the wrong on-disk destination shape.

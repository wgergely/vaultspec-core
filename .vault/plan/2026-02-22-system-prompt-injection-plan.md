---
tags:
  - "#plan"
  - "#system-prompt-injection"
date: "2026-02-22"
related:
  - "[[2026-02-22-system-prompt-injection-research]]"
  - "[[2026-02-22-system-prompt-injection-adr]]"
---
# Plan: XML-Based System Prompt Injection

This plan executes the refactor of `src/vaultspec/cli.py` to use XML-based injection for skills and sub-agents, as mandated by `[[2026-02-22-system-prompt-injection-adr]]`.

## Phase 1: Preparation
- [ ] Verify `skills-ref` library availability in the environment (installed from local `tmp-ref/agentskills` or via pip if published).
- [ ] Inspect `src/vaultspec/cli.py` to identify import locations and `_collect_*_listing` functions.

## Phase 2: Implementation
- [ ] **Step 1: Update Imports**
    - [ ] Import `to_prompt` from `skills_ref.prompt` (handling potential import errors gracefully or ensuring dependency is present).
    - [ ] Add necessary imports for XML handling (if needed for sub-agents).

- [ ] **Step 2: Refactor `collect_skills`**
    - [ ] Update `collect_skills` (or create a helper) to return a list of `Path` objects to skill directories, as expected by `to_prompt`.
    - [ ] The current `collect_skills` returns a dictionary of metadata; we might need to adjust or create a focused `get_skill_dirs` helper.

- [ ] **Step 3: Update `_collect_skill_listing`**
    - [ ] Replace Markdown list logic with a call to `skills_ref.prompt.to_prompt(skill_dirs)`.

- [ ] **Step 4: Update `_collect_agent_listing`**
    - [ ] Refactor to generate `<available_subagents>` XML block.
    - [ ] Iterate over agents and create `<subagent>` elements with `<name>`, `<description>`, and `<tier>`.

## Phase 3: Verification
- [ ] **Step 1: Manual Test**
    - [ ] Run `python src/vaultspec/cli.py system show` and inspect the output.
    - [ ] Confirm `<available_skills>` block is present and contains valid XML with `<location>`.
    - [ ] Confirm `<available_subagents>` block is present and valid.
- [ ] **Step 2: Sync Test**
    - [ ] Run `python src/vaultspec/cli.py system sync --dry-run` to verify expected changes to `SYSTEM.md` files.

## Phase 4: Cleanup
- [ ] Remove any temporary test scripts.

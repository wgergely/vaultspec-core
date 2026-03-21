---
tags:
  - '#plan'
  - '#skill-audit'
date: '2026-02-22'
related:
  - '[[2026-02-22-skill-audit-adr]]'
---

# Plan: Refactor Skills to Spec

This plan executes the restructuring of `.vaultspec/rules/skills` to comply with the Agent Skills specification.

## Phase 1: Preparation

- [ ] Verify `skills-ref` tool availability (installed or via cloned repo).
- [ ] List all target skill files in `.vaultspec/rules/skills`.

## Phase 2: Migration

- [ ] For each `vaultspec-*.md` file:
  - [ ] Create directory `.vaultspec/rules/skills/<name>`.
  - [ ] Move file to `.vaultspec/rules/skills/<name>/SKILL.md`.
  - [ ] Inject `name: <name>` into YAML frontmatter.
  - [ ] Remove the original flat file (if not done by move).

## Phase 3: Validation

- [ ] Run `skills-ref validate` on each new skill directory.
- [ ] Verify that no flat `.md` files remain in `.vaultspec/rules/skills`.

## Phase 4: Cleanup

- [ ] Remove any temporary files or logs.

---
tags:
  - '#plan'
  - '#agent-removal'
date: '2026-03-05'
related:
  - '[[2026-03-05-agent-removal-adr]]'
  - '[[2026-03-05-agent-removal-research]]'
  - '[[2026-03-05-agent-removal-reference]]'
---

# `agent-removal` plan

Implement the removal of obsolete agent management and A2A protocol from the core repository to achieve a squeaky clean state without agent-wrangling logic.

## Proposed Changes

Remove all obsolete agent management, A2A protocol, subagent, and team coordination code as detailed in `2026-03-05-agent-removal-adr`. This code has been migrated to `vaultspec-a2a`, and its removal from the core `vaultspec` repository will reduce bloat, simplify the codebase, and align with our new architecture. The cleanup involves removing CLI commands, MCP tools, orchestration logic, the entire A2A protocol layer, updating core entry points, and removing associated tests.

## Tasks

- Phase 1: Remove CLI Commands and MCP Tools
  - Name: Delete CLI entry points and MCP tools
  - Step summary: `.vault/exec/2026-03-05-agent-removal/2026-03-05-agent-removal-phase1-step1.md`
  - Executing sub-agent: `vaultspec-standard-executor`
  - References: `2026-03-05-agent-removal-adr`, `2026-03-05-agent-removal-research`
- Phase 2: Remove Library Code and Protocol Layer
  - Name: Delete orchestration logic and A2A directory
  - Step summary: `.vault/exec/2026-03-05-agent-removal/2026-03-05-agent-removal-phase2-step1.md`
  - Executing sub-agent: `vaultspec-standard-executor`
  - References: `2026-03-05-agent-removal-adr`, `2026-03-05-agent-removal-reference`
  - Name: Remove A2A methods from providers
  - Step summary: `.vault/exec/2026-03-05-agent-removal/2026-03-05-agent-removal-phase2-step2.md`
  - Executing sub-agent: `vaultspec-standard-executor`
  - References: `2026-03-05-agent-removal-reference`
- Phase 3: Update Core Entry Points and Configuration
  - Name: Clean up __main__, spec_cli, and __init__
  - Step summary: `.vault/exec/2026-03-05-agent-removal/2026-03-05-agent-removal-phase3-step1.md`
  - Executing sub-agent: `vaultspec-complex-executor`
  - References: `2026-03-05-agent-removal-adr`, `2026-03-05-agent-removal-research`
  - Name: Remove A2A configurations, enums, and types
  - Step summary: `.vault/exec/2026-03-05-agent-removal/2026-03-05-agent-removal-phase3-step2.md`
  - Executing sub-agent: `vaultspec-complex-executor`
  - References: `2026-03-05-agent-removal-research`
- Phase 4: Clean up Test Suite
  - Name: Delete A2A and agent tests
  - Step summary: `.vault/exec/2026-03-05-agent-removal/2026-03-05-agent-removal-phase4-step1.md`
  - Executing sub-agent: `vaultspec-standard-executor`
  - References: `2026-03-05-agent-removal-reference`

## Parallelization

Phases 1, 2, and 4 largely involve deleting independent files or specific directories and can be run in parallel by `vaultspec-standard-executor` instances.
Phase 3 involves modifying central shared files like `__main__.py` and `config.py`. It should be handled sequentially or after the deletions are mostly complete by `vaultspec-complex-executor` to avoid conflicts and ensure core functionality routing remains intact.

## Verification

Run the complete test suite using `pytest` to ensure all tests pass and no core components inadvertently relied on removed A2A logic.
Verify via CLI that `vaultspec team`, `vaultspec server`, `vaultspec subagent`, and `vaultspec agents` commands fail with expected "command not found" errors without crashing.
Ensure the MCP server starts correctly without throwing errors about missing `subagent_tools` or `team_tools`.
Audit the `src/vaultspec` codebase using tools like `rg` for keywords like `a2a`, `subagent`, `team_session` to confirm no straggling references remain.

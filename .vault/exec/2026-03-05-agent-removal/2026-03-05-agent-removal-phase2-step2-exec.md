---
tags:
  - '#exec'
  - '#agent-removal'
date: '2026-03-05'
related:
  - '[[2026-03-05-agent-removal-plan]]'
---

# `agent-removal` `phase2` `step2`

Phase 2: Remove Library Code and Protocol Layer. Removed A2A methods and references from providers.

- Modified: `[[src/vaultspec/protocol/providers/base.py]]`
- Modified: `[[src/vaultspec/protocol/providers/claude.py]]`
- Modified: `[[src/vaultspec/protocol/providers/gemini.py]]`
- Modified: `[[src/vaultspec/protocol/providers/__init__.py]]`

## Description

Removed the `ProcessSpec` class and the `prepare_process` abstract method from `AgentProvider` in `base.py`.
In `claude.py` and `gemini.py`, removed the implementations of `prepare_process`, A2A-specific OAuth token management, version checking, and related constants.
Cleaned up unused imports in all modified files.

## Tests

Manual verification that the methods and constants are removed.
Further validation via `pytest` is expected to fail until Phase 4 (Test Suite Cleanup) is completed.

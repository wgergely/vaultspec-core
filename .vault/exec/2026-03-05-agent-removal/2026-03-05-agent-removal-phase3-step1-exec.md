---
tags:
  - '#exec'
  - '#agent-removal'
date: '2026-03-05'
related:
  - '[[2026-03-05-agent-removal-plan]]'
---

# `agent-removal` `phase3` `step1`

Phase 3: Update Core Entry Points and Configuration. Cleaned up `__main__`, `spec_cli`, and `__init__`.

- Modified: `[[src/vaultspec/__main__.py]]`
- Modified: `[[src/vaultspec/spec_cli.py]]`
- Modified: `[[src/vaultspec/__init__.py]]`

## Description

Removed obsolete commands and namespaces from the CLI entry points:

- Removed `team`, `server`, `subagent`, and `mcp` from `src/vaultspec/__main__.py`.
- Removed `agents` command and related dispatch logic from `src/vaultspec/spec_cli.py`.
- Updated `sync-all` to no longer sync agents.
- Cleaned up docstrings in `src/vaultspec/__init__.py`.
- Removed `orchestration`, `subagent`, and `mcp_tools` from the `test` command choices.

## Tests

Manual verification that the commands are removed from `--help` output.
Further validation via `pytest` is expected to fail until Phase 4 (Test Suite Cleanup) is completed.

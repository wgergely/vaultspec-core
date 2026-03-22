---
tags:
  - '#exec'
  - '#agent-removal'
date: '2026-03-05'
related:
  - '[[2026-03-05-agent-removal-plan]]'
---

# `agent-removal` `phase3` `step2`

Phase 3: Update Core Entry Points and Configuration. Removed A2A configurations, enums, and types.

- Modified: `[[src/vaultspec/core/enums.py]]`
- Modified: `[[src/vaultspec/core/types.py]]`
- Modified: `[[src/vaultspec/config/config.py]]`

## Description

Cleaned up core enums, types, and configuration by removing obsolete agent and A2A references:

- Removed `AGENTS` from `Tool`, `Resource`, `FileName`, and `DirName` enums.
- Removed `AGENTS_SRC_DIR` global and its initialization.
- Removed `Tool.AGENTS` and `Tool.ANTIGRAVITY` from `TOOL_CONFIGS`.
- Removed all agent-related and A2A-related attributes (`agent_mode`, `a2a_host`, etc.) and their corresponding `ConfigVariable` entries from `VaultSpecConfig`.

## Tests

Manual verification that the core logic no longer references these obsolete components.
Further validation via `pytest` is expected to fail until Phase 4 (Test Suite Cleanup) is completed.

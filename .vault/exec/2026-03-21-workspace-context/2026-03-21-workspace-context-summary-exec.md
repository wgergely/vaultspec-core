---
tags:
  - '#exec'
  - '#workspace-context'
date: '2026-03-21'
related:
  - '[[2026-03-21-workspace-context-plan]]'
---

# workspace-context summary

Eliminated all 9 module-level mutable globals from `types.py`, replacing them with a frozen `WorkspaceContext` dataclass backed by `contextvars.ContextVar`.

- Modified: `src/vaultspec_core/core/types.py`
- Modified: `src/vaultspec_core/core/__init__.py`
- Modified: `src/vaultspec_core/core/commands.py`
- Modified: `src/vaultspec_core/core/config_gen.py`
- Modified: `src/vaultspec_core/core/manifest.py`
- Modified: `src/vaultspec_core/core/rules.py`
- Modified: `src/vaultspec_core/core/skills.py`
- Modified: `src/vaultspec_core/core/agents.py`
- Modified: `src/vaultspec_core/core/system.py`
- Modified: `src/vaultspec_core/cli/_target.py`
- Modified: `src/vaultspec_core/cli/root.py`
- Modified: `src/vaultspec_core/cli/spec_cmd.py`
- Modified: `src/vaultspec_core/cli/vault_cmd.py`
- Modified: `src/vaultspec_core/hooks/engine.py`
- Modified: `src/vaultspec_core/mcp_server/vault_tools.py`
- Modified: 8 test files

## Description

- Phase 1: Defined `WorkspaceContext`, `ContextVar`, `get_context()`, `set_context()`. Deleted 9 globals.
- Phase 2: Migrated all 22 consumer files from `_t.TARGET_DIR` to `_t.get_context().target_dir` (etc).
- Phase 3: Replaced swap-and-restore in `sync_provider` with `contextvars.copy_context().run()`.
- Phase 4: Fixed `_ensure_tool_configs` TOCTOU race with `tempfile.mkdtemp()`. Added `skip = list(skip)` defense. Moved validation before context mutation in `uninstall_run`.
- Phase 5: Added `_isolated_context` decorator to MCP tool handlers for per-request isolation.

## Tests

757 tests pass. Zero module-level mutable state remains in `types.py`. Grep verification confirms no old global names referenced outside definitions.

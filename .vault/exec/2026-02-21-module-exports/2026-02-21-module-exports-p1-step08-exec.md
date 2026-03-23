---
tags:
  - '#exec'
  - '#module-exports'
date: '2026-02-21'
related:
---

# Step 8: Retarget entry point imports and add `__all__` to top-level modules

## Status: COMPLETE

## Summary

Added `__all__` exports to top-level modules and the `mcp_tools` package, converted `__main__.py` to use a relative import, and verified all CLI entry points use package-level imports where available.

## Changes

### 8a. `__all__` on top-level modules

- `src/vaultspec/logging_config.py` -- added `__all__ = ["configure_logging", "reset_logging"]`
- `src/vaultspec/mcp_tools/vault_tools.py` -- added `__all__ = ["register_tools"]`
- `src/vaultspec/mcp_tools/team_tools.py` -- added `__all__ = ["register_tools"]`
- `src/vaultspec/mcp_tools/framework_tools.py` -- added `__all__ = ["register_tools"]`

### 8b. `mcp_tools/__init__.py` re-exports

Replaced the docstring-only `__init__.py` with disambiguated re-exports:

- `register_framework_tools`
- `register_team_tools`
- `register_vault_tools`

### 8c. `__main__.py` relative import

Converted `from vaultspec.cli import main` to `from .cli import main`.

### 8d. CLI entry point import audit

Verified all five CLI files (`cli.py`, `vault_cli.py`, `team_cli.py`, `subagent_cli.py`, `server.py`). All imports already target package-level exports where available. Remaining deep imports are intentional by design:

- `orchestration.team` (team_cli.py) -- no package-level re-export by design
- `orchestration.subagent` (subagent_cli.py) -- no package-level re-export by design
- `subagent_server.server` (subagent_cli.py) -- `main as server_main` aliased import
- `protocol.a2a.executors` (subagent_cli.py) -- not re-exported from `protocol.a2a`

## Verification

All modified modules import cleanly:

- `python -c "from vaultspec.mcp_tools import register_framework_tools, ..."` -- OK
- `python -c "from vaultspec.logging_config import configure_logging, reset_logging"` -- OK
- `python -m vaultspec --help` -- OK
- Grep for deep imports in CLI files confirmed only intentional exceptions remain.

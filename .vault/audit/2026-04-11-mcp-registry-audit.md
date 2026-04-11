---
tags:
  - '#audit'
  - '#mcp-registry'
date: '2026-04-11'
related:
  - '[[2026-04-11-mcp-registry-adr]]'
  - '[[2026-04-11-mcp-registry-phase1-plan]]'
---

# `mcp-registry` Code Review

## CORRECT-001 | HIGH | `--skip mcp` not respected in `_run_all_syncs()`

`_run_all_syncs()` unconditionally calls `_mcp_sync`. The `skip` set is
not consulted for `"mcp"` because it only filters `Tool` enum members.
Must gate the `_mcp_sync` call on `"mcp" not in skip`.

**Status:** FIXED

## DIAG-002 / CORRECT-002 | MEDIUM | Hardcoded `vaultspec-core` guard in `collect_mcp_config_state()`

The collector returns `PARTIAL_MCP` if `"vaultspec-core"` is not in
servers before checking registry drift. This gates the registry check
and misclassifies workspaces that use only custom servers. Fix: replace
hardcoded check with registry-aware presence check.

**Status:** FIXED

## DIAG-001 | MEDIUM | `REGISTRY_DRIFT` silently no-op in resolver

`_resolve_config()` groups `REGISTRY_DRIFT` with `OK`/`PARTIAL_MCP`/
`USER_MCP` in a no-op return. Intent is advisory-only (doctor surfaces
it, sync repairs it via `_run_all_syncs`). This is correct behavior:
sync already repairs drift by re-merging definitions. No fix needed.

**Status:** BY DESIGN

## DIAG-003 | LOW | Absolute import in `collectors.py`

`from vaultspec_core.core.mcps import collect_mcp_servers` should use
relative import. Fixed for consistency.

**Status:** FIXED

## SAFETY-001 | LOW | `mcp_uninstall` silently swallows parse errors

Returns empty list on corrupt `.mcp.json` with no logging. Acceptable
since uninstall is best-effort cleanup; corrupt files require manual
intervention regardless.

**Status:** WONTFIX

## QUAL-001 | LOW | No dict validation in `mcp_add()`

`mcp_add()` does not validate config is a dict. `collect_mcp_servers()`
catches non-dicts on read. Acceptable layering.

**Status:** WONTFIX

## ARCH-003 | LOW | Module docstring not updated

`spec_cmd.py` docstring doesn't mention `mcps_app`. Fixed.

**Status:** FIXED

## TEST-001 | MEDIUM | No test for missing context error path

`mcp_sync()` LookupError guard not tested. Test added.

**Status:** FIXED

## COMPLETE-002 | LOW | Missing CLI integration tests (Step 6.4)

Typer runner CLI tests deferred to follow-up. Core logic is covered
by unit and lifecycle tests.

**Status:** DEFERRED

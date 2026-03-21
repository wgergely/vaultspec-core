---
tags:
  - '#exec'
  - '#workspace-context'
date: '2026-03-21'
related:
  - '[[2026-03-21-workspace-context-plan]]'
---

# workspace-context phase 3-5 execution

## Phase 3 - eliminate swap-and-restore in sync_provider

Replaced two swap-and-restore patterns in `sync_provider` with
`contextvars.copy_context().run(...)`:

- The `provider == "all"` branch (with skip filtering) now defines
  `_sync_all_with_configs` and runs it inside a copied context. The `finally`
  restore block is removed.
- The per-provider branch defines `_sync_single_provider` and runs it the same
  way. The `finally` restore block is removed.

Both patterns no longer mutate the caller's context - the copied context is
discarded automatically when `run()` returns.

## Phase 4 - fix \_ensure_tool_configs and entry points

- Replaced the real `.vaultspec/` directory creation in `_ensure_tool_configs`
  with `tempfile.mkdtemp()`. The function now creates a temp scaffold,
  resolves the workspace layout from it, then constructs a `WorkspaceLayout`
  with the real target path so tool_configs reference the actual workspace.
  No `finally` cleanup block needed.
- Moved `_validate_provider` and `_validate_skip` calls before the
  `set_context()` bootstrap in `uninstall_run`, fixing CORE-L4
  (pre-validation mutation).
- Added `skip = list(skip or [])` at the top of `cmd_install`,
  `cmd_uninstall`, and `cmd_sync` in `root.py` to defend against mutable
  Typer defaults (CLI-H2).

## Phase 5 - MCP handler per-request context

- Added `_isolated_context` decorator in `vault_tools.py` that snapshots
  the current `WorkspaceContext` before each handler invocation and restores
  it in a `finally` block. Applied to both `find` and `create` tool handlers.
- This prevents mutations within a handler from leaking to other concurrent
  MCP requests.

## Verification

- Full test suite: 757 passed, 0 failed (excluding `test_vault_stats`).
- No swap-and-restore `finally` blocks remain in `sync_provider`.
- `_ensure_tool_configs` no longer creates or deletes directories at real
  workspace paths.

## Files changed

- `src/vaultspec_core/core/commands.py` - phases 3 and 4
- `src/vaultspec_core/cli/root.py` - phase 4 (mutable default defense)
- `src/vaultspec_core/mcp_server/vault_tools.py` - phase 5

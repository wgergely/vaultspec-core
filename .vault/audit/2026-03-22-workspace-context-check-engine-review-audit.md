---
tags:
  - '#audit'
  - '#workspace-context'
date: '2026-03-22'
related:
  - '[[2026-03-21-workspace-context-plan]]'
  - '[[2026-03-21-check-engine-perf-plan]]'
  - '[[2026-03-21-feature-documentation-code-review-audit]]'
---

# workspace-context and check-engine-perf post-execution review

## WorkspaceContext Migration

WC-001 | MEDIUM | `_isolated_context` uses save/restore instead of `copy_context().run()`
`vault_tools.py:36-55` - The MCP decorator saves/restores context manually. Under concurrent async, two coroutines can race on the same ContextVar. The plan required `copy_context().run()`. Current handlers are read-only so no bug yet, but will silently break when any handler calls `set_context()`.

WC-002 | LOW | `_ensure_tool_configs` leaks temporary directory
`commands.py:333` - `tempfile.mkdtemp()` created but never cleaned up. Each invocation on a fresh project leaves an orphaned temp dir.

WC-003 | LOW | `tool_configs` is mutable dict on frozen dataclass
`types.py:123` - `dict[Tool, ToolConfig]` is mutable despite `frozen=True`. No code currently mutates in-place, but the contract is unenforced.

WC-004 | INFO | Stale docstring references to old globals
`sync.py:248`, `app.py:95`, `test_hooks.py:356` - Comments mention deleted globals by name.

WC-005 | INFO | `init_paths` accepts `Any` type for `layout`
`types.py:172` - Could be `Union[WorkspaceLayout, Path]` for better type safety.

## Check Engine Performance

CE-001 | MEDIUM | VaultGraph.\_build_graph still reads every file twice
`graph/api.py:292,353` - Pass 1 reads files for metadata, Pass 2 re-reads for link extraction. Body is already stored on DocNode from Pass 1. Undermines "1N reads" target.

CE-007 | INFO | Plan text says "optional parameters" but ADR and implementation use required
Plan line 23 vs ADR line 33. Implementation correctly follows the ADR.

## Test Migration

TM-001 | MEDIUM | `_isolate_state` cannot restore context to "unset"
`conftest.py:124-129` - When no context existed before a test, teardown cannot clear the ContextVar. Tests that call `init_paths` leak context. Should use token-based save/restore like `test_sync_manifest.py` does.

TM-009 | LOW | `_isolate_state` only covers `src/vaultspec_core/tests/cli/`
Tests in outer `tests/` directory have no context isolation fixture. Context leaks between test trees if collected in same session.

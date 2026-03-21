---
tags:
  - '#research'
  - '#workspace-context'
date: '2026-03-21'
related:
  - '[[2026-03-21-feature-documentation-code-review-audit]]'
---

# workspace-context research: global mutable state

The vaultspec-core codebase uses 9 module-level mutable globals in
`src/vaultspec_core/core/types.py` to hold workspace paths and tool
configuration. This research documents the inventory, mutation patterns,
concurrency risks, and candidate solutions.

## Findings

### globals inventory

All 9 globals are declared at module level in `types.py` and initialised to
empty values:

- `ROOT_DIR` - workspace root path
- `TARGET_DIR` - alias for `ROOT_DIR`
- `RULES_SRC_DIR` - rules source directory
- `SKILLS_SRC_DIR` - skills source directory
- `AGENTS_SRC_DIR` - agents source directory
- `SYSTEM_SRC_DIR` - system source directory
- `TEMPLATES_DIR` - templates directory
- `HOOKS_DIR` - hooks directory
- `TOOL_CONFIGS` - mutable dict mapping `Tool` to `ToolConfig`

### mutation points

- **`init_paths()`** bulk-sets all 9 globals. Called from 6 locations across
  CLI entry points and test fixtures.
- **`TARGET_DIR`** is directly assigned in `install_run`, `uninstall_run`, and
  `apply_target_install` before the function body uses it for validation. In
  `uninstall_run` the assignment happens before validation, meaning an invalid
  target still mutates the global (CORE-L4).
- **`TOOL_CONFIGS`** is temporarily replaced inside `sync_provider` using a
  swap-and-restore pattern (save reference, assign new dict, restore in
  `finally`). Two call sites use this pattern. Any concurrent caller sees the
  swapped dict during the window (CORE-H1).
- **`_ensure_tool_configs`** creates a temporary `.vaultspec/` directory at the
  real workspace path, then deletes it in a `finally` block. Between creation
  and deletion another process could observe or interfere with the directory
  (TOCTOU race, CORE-H2).

### concurrency risk assessment

The MCP server runs as an async event loop. All MCP tool handlers share the
same module-level globals. Currently the exposed MCP tools are read-only, so no
corruption occurs in practice. However:

- No protection mechanism exists to prevent future write-capable MCP tools from
  hitting the swap-and-restore race.
- If two async tasks ever call `sync_provider` concurrently (e.g. via a
  programmatic API), the `TOOL_CONFIGS` swap corrupts both tasks.
- The `TARGET_DIR` pre-validation mutation in `uninstall_run` is a latent bug
  that would surface under programmatic (non-CLI) usage.

### mutable default parameter

CLI commands use `skip: list[str] = []` as a Typer parameter default. Typer
instantiates a fresh list per invocation, so this is safe at the CLI boundary.
Under programmatic reuse the shared default would accumulate mutations across
calls (CLI-H2).

### temp directory race

`_ensure_tool_configs` creates `.vaultspec/` at the real workspace path to
satisfy `init_paths`, then deletes it. Using `tempfile.mkdtemp` instead would
eliminate the TOCTOU window entirely.

### solution options

**Option A - `WorkspaceContext` dataclass passed as parameter.** Define a
frozen dataclass holding all 9 values. Every function receives it explicitly.
Most explicit, but requires touching every function signature across the
codebase in a single change.

**Option B - `contextvars.ContextVar`.** Store a `WorkspaceContext` in a
`ContextVar`. Each async task or CLI invocation sets its own copy. Smaller
change surface, but loses the explicitness of parameter passing.

**Option C - hybrid with compatibility shim.** Introduce `WorkspaceContext`
dataclass and store it in a `ContextVar`. Keep the 9 module-level names as thin
read-only properties (or a deprecation proxy) that delegate to the current
context value. Allows incremental migration: new code uses the context
directly, old code continues to work via the shim.

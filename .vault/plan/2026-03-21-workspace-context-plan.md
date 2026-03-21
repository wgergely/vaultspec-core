---
tags:
  - '#plan'
  - '#workspace-context'
date: '2026-03-21'
related:
  - '[[2026-03-21-workspace-context-adr]]'
  - '[[2026-03-21-workspace-context-research]]'
---

# workspace-context plan

Eliminate global mutable state in `types.py` by introducing a frozen
`WorkspaceContext` dataclass backed by `contextvars.ContextVar`. No backward
compatibility shim -- clean migration of all callers. Fixes CORE-H1
(swap-and-restore race), CORE-H2 (temp dir TOCTOU), CORE-L4 (pre-validation
mutation), and CLI-H2 (mutable default).

## Proposed Changes

Per \[[2026-03-21-workspace-context-adr]\], adopt a direct migration with no
compatibility layer. The work splits into five phases executed in a single PR.
The \[[2026-03-21-workspace-context-research]\] documents the 9 globals, their
6 `init_paths` call sites, the 2 swap-and-restore sites in `sync_provider`,
and the `_ensure_tool_configs` race.

## Tasks

<!-- IMPORTANT: This document must be updated between execution runs to
     track progress. -->

- Phase 1 - define `WorkspaceContext`, `ContextVar`, and `get_context()`

  1. Create a frozen `WorkspaceContext` dataclass in `types.py` with fields
     mirroring the 9 globals (`root_dir`, `target_dir`, `rules_src_dir`,
     `skills_src_dir`, `agents_src_dir`, `system_src_dir`, `templates_dir`,
     `hooks_dir`, `tool_configs`)
  1. Add a module-level `_workspace_ctx: ContextVar[WorkspaceContext]`
  1. Add a `get_context() -> WorkspaceContext` accessor function
  1. Modify `init_paths()` to build a `WorkspaceContext`, set the `ContextVar`,
     and return the context object
  1. Delete all 9 bare module globals (`ROOT_DIR`, `TARGET_DIR`, etc.)

- Phase 2 - migrate all consumers from globals to context

  1. Replace every `_t.TARGET_DIR` with `_t.get_context().target_dir` (and
     likewise for all other fields) across all source files
  1. Replace every `_t.TOOL_CONFIGS` with `_t.get_context().tool_configs`
  1. Update all test fixtures that directly assign globals to use
     `init_paths()` or `_workspace_ctx.set()`

- Phase 3 - eliminate swap-and-restore in `sync_provider`

  1. In each `sync_provider` call site, replace the swap-and-restore pattern
     with `contextvars.copy_context().run(...)` passing a new
     `WorkspaceContext` that carries the provider-specific `tool_configs`
  1. Remove the `finally` restore blocks
  1. Add a test that runs two `sync_provider` calls concurrently and verifies
     no cross-contamination of `tool_configs`

- Phase 4 - fix `_ensure_tool_configs` and entry points

  1. Replace the real `.vaultspec/` directory creation in
     `_ensure_tool_configs` with `tempfile.mkdtemp()`
  1. Remove the `finally` deletion block
  1. Update `install_run`, `uninstall_run`, `apply_target_install` to set
     the context var via `init_paths()` instead of direct global assignment
  1. Move validation before context assignment in `uninstall_run` (fixes
     CORE-L4)
  1. Add `skip = list(skip)` at the top of every Typer command that accepts a
     `skip` parameter (fixes CLI-H2)

- Phase 5 - MCP handler per-request context

  1. In the MCP server's request dispatch, wrap each handler invocation in
     `contextvars.copy_context().run(...)` so every request gets an isolated
     context snapshot
  1. Add an integration test that sends concurrent MCP requests and verifies
     context isolation

## Parallelization

Phase 1 is prerequisite to all others. Phase 2 must follow phase 1. Phases
3, 4, and 5 are independent after phase 2 and can proceed in parallel. All
phases land in a single PR -- no incremental shim.

## Verification

- All existing tests pass after full migration (no regressions).
- A concurrent `sync_provider` test (phase 3) proves no `TOOL_CONFIGS`
  cross-contamination.
- Grep verification: no `_t.TARGET_DIR`, `_t.TOOL_CONFIGS`, or any of the 9
  old global names appear outside of `types.py` definitions.
- No swap-and-restore pattern remains in the codebase (grep verification).
- A concurrent MCP request test (phase 5) proves per-request context
  isolation.
- `_ensure_tool_configs` no longer creates or deletes directories at real
  workspace paths (phase 4).

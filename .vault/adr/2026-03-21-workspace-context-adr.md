---
tags:
  - '#adr'
  - '#workspace-context'
date: '2026-03-21'
related:
  - '[[2026-03-21-workspace-context-research]]'
  - '[[2026-03-21-feature-documentation-code-review-audit]]'
---

# workspace-context adr: context-var migration | (**status:** `accepted`)

## Problem Statement

The codebase relies on 9 module-level mutable globals in `types.py` for
workspace paths and tool configuration. The `sync_provider` function uses a
swap-and-restore pattern on `TOOL_CONFIGS` that is unsafe under concurrency.
`_ensure_tool_configs` creates a real directory with a TOCTOU race window.
`uninstall_run` mutates `TARGET_DIR` before validation. These patterns are
incompatible with the async MCP server model and programmatic reuse.

## Considerations

- The MCP server runs all handlers in a shared async event loop with shared
  module state. Future write-capable tools would hit the swap race immediately.
- Option A (`WorkspaceContext` as explicit parameter) is the cleanest but
  requires changing every function signature.
- Option B (`ContextVar` alone) provides async safety but makes data flow
  implicit.
- Option C (hybrid with backward-compatible shim) adds complexity and delays
  the migration.

## Constraints

- No backward compatibility layer -- delete module globals, migrate all callers
  in one pass. Clean cut over shim debt.
- `tempfile.mkdtemp` is available in the stdlib and sufficient for the temp
  directory fix.

## Implementation

Introduce a frozen `WorkspaceContext` dataclass holding `root_dir`,
`target_dir`, `rules_src_dir`, `skills_src_dir`, `agents_src_dir`,
`system_src_dir`, `templates_dir`, `hooks_dir`, and `tool_configs`. Store the
active context in a `contextvars.ContextVar[WorkspaceContext]`.

Modify `init_paths()` to return a `WorkspaceContext` and set the `ContextVar`.
Delete the 9 module-level globals entirely. All consumers migrate from
`_t.TARGET_DIR` to reading from the context var via a `get_context()` accessor
or by receiving the context as a parameter. See
\[[2026-03-21-workspace-context-research]\] for the full globals inventory and
mutation point analysis.

Replace swap-and-restore in `sync_provider` with a scoped context copy:
create a new `WorkspaceContext` with the provider-specific `tool_configs`,
run the sync in a `contextvars.copy_context()`, and discard the copy
afterwards.

Replace `_ensure_tool_configs` real-directory creation with
`tempfile.mkdtemp`.

Add `skip = list(skip)` copy defense in CLI commands that accept mutable
defaults.

## Rationale

A clean migration was chosen over a shim-based approach to avoid accumulating
compatibility debt. The globals pattern is the root cause of multiple HIGH
findings, and a shim only delays the inevitable full migration while adding
cognitive load. The research in \[[2026-03-21-workspace-context-research]\]
confirmed all mutation points are enumerable and the migration is mechanical.
The `ContextVar` provides async safety for MCP, while explicit `get_context()`
gives clear data flow.

## Consequences

- Every file that reads `_t.TARGET_DIR` or `_t.TOOL_CONFIGS` must be updated
  in a single PR. This is a large but mechanical change.
- Test fixtures that assign globals directly must be rewritten to use
  `init_paths()` or context-setting helpers.
- No shim means no gradual migration -- the cut is clean but the PR is large.
- After migration, the codebase has zero module-level mutable state in
  `types.py`.

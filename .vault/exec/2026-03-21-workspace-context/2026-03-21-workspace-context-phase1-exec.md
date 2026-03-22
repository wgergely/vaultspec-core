---
tags:
  - '#exec'
  - '#workspace-context'
date: '2026-03-21'
related:
  - '[[2026-03-21-workspace-context-plan]]'
---

# workspace-context phase1-exec

## Objective

Define `WorkspaceContext`, `ContextVar`, `get_context()`, and `set_context()`
in `types.py`. Delete all 9 bare module globals. Update `init_paths()` to build
and store a `WorkspaceContext`. Update `core/__init__.py` re-exports.

## Changes

- `src/vaultspec_core/core/types.py`

  - Added `contextvars.ContextVar` import
  - Added frozen `WorkspaceContext` dataclass with 9 fields mirroring the
    deleted globals (`root_dir`, `target_dir`, `rules_src_dir`,
    `skills_src_dir`, `agents_src_dir`, `system_src_dir`, `templates_dir`,
    `hooks_dir`, `tool_configs`)
  - Added module-level `_workspace_ctx: ContextVar[WorkspaceContext]` with no
    default (accessing before `init_paths()` raises `LookupError`)
  - Added `get_context() -> WorkspaceContext` accessor
  - Added `set_context(ctx: WorkspaceContext) -> None` setter
  - Modified `init_paths()` to build a `WorkspaceContext`, call
    `_workspace_ctx.set(ctx)`, and return the context object
  - Removed all `global` declarations and direct global assignments from
    `init_paths()`
  - Deleted the 9 bare module globals: `ROOT_DIR`, `TARGET_DIR`,
    `RULES_SRC_DIR`, `SKILLS_SRC_DIR`, `AGENTS_SRC_DIR`, `SYSTEM_SRC_DIR`,
    `TEMPLATES_DIR`, `HOOKS_DIR`, `TOOL_CONFIGS`

- `src/vaultspec_core/core/__init__.py`

  - Removed re-exports of the 9 deleted globals
  - Added re-exports: `WorkspaceContext`, `get_context`, `set_context`
  - Retained: `CONFIG_HEADER`, `SyncResult`, `ToolConfig`, `init_paths`
  - Updated module docstring to reference `WorkspaceContext` instead of
    `ROOT_DIR`

## Verification

```
python -c "from vaultspec_core.core.types import WorkspaceContext, get_context, set_context, init_paths; print('OK')"
# Output: OK
```

## Known breakage

All consumers that reference `_t.TARGET_DIR`, `_t.TOOL_CONFIGS`, etc. will
have import errors. This is expected and will be resolved in Phase 2.

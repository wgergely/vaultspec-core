---
tags:
  - "#exec"
  - "#commands-review"
date: 2026-02-05
related:
  - "[[2026-02-05-commands-reference]]"
---

# commands-review analysis

**Date:** 2026-02-05
**Task:** Review `api/commands.rs` for Action System Conflicts

## Files Modified

None (analysis only)

## Files Reviewed

1. `crates/pp-editor-core/src/api/commands.rs` - Command handler trait
2. `crates/pp-editor-core/src/api/context.rs` - Provider context for commands
3. `crates/pp-editor-events/src/actions.rs` - GPUI action definitions
4. `crates/pp-editor-events/src/dispatch.rs` - Action dispatch system
5. `crates/pp-editor-events/src/keymap.rs` - Keybinding system
6. `legacy/editor/providers/src/command_registry.rs` - Legacy command registry
7. `legacy/editor/providers/src/prompt_command.rs` - Example @prompt command

## Key Findings

### System Separation

The `@command` system and action system are architecturally distinct:

**@command System:**

- Async text-based handlers for LLM/plugin integration
- Example: `@prompt list files` → generates shell command
- Uses string-based dispatch with `CommandRegistry`
- Returns text to be inserted into editor
- Supports cancelation for long-running operations

**Action System:**

- Sync keyboard-driven UI commands via GPUI
- Example: `ctrl-k ctrl-d` → `editor::DeleteLine`
- Uses type-based dispatch through `DispatchTree`
- Executes immediately in UI event loop
- Focus-aware with context filtering

### No Conflicts Found

The systems operate at different layers:

- Commands: **Content generation** (AI, file loading, web search)
- Actions: **User interaction** (keyboard input, cursor movement, editing)

### Integration Points

They complement each other in the markdown editor:

1. **User types** → handled by actions (keyboard events)
2. **Parser detects @command** → async execution via command system
3. **Command returns result** → insertion via actions

## Recommendation

**KEEP SEPARATE** - The systems serve distinct purposes with different execution models. Attempting to merge would create async/sync conflicts and lose type safety.

## Next Steps

Document created: `.docs/audit/2026-02-05-commands-review.md`

This provides:

- Detailed comparison of both systems
- Integration recommendations for GPUI event loop
- Suggested crate structure for command implementations
- Future considerations for command/action bridge

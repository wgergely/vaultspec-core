---
tags:
  - "#exec"
  - "#remove-deprecated-input-modules"
date: 2026-02-05
related:
  - "[[2026-02-05-editor-demo-displaymap-reference]]"
---

# remove-deprecated-input-modules step-1

## Modified Files

1. `Y:\code\popup-prompt-worktrees\main\crates\pp-editor-core\src\lib.rs`
2. Deleted: `Y:\code\popup-prompt-worktrees\main\crates\pp-editor-core\src\input.rs`
3. Deleted: `Y:\code\popup-prompt-worktrees\main\crates\pp-editor-core\src\input_handler.rs`

## Key Changes

### lib.rs Modifications

- Removed `pub mod input;` declaration (line 11)
- Removed `pub mod input_handler;` declaration (line 12)
- Removed re-exports from `input` module:
  - `EditorInputEvent`, `ImeEvent`, `Key`, `KeyEvent`, `Modifiers`
  - `MouseButton`, `MouseEvent`, `MousePos`, `NamedKey`
  - `ScrollDelta`, `ScrollEvent`
- Removed re-exports from `input_handler` module:
  - `DefaultInputHandler`, `InputHandled`, `InputHandler`, `StatefulInputHandler`

### Deleted Files

1. **input.rs**: Contained deprecated event type definitions that conflicted with `pp-editor-events` crate
2. **input_handler.rs**: Contained deprecated input handler traits incompatible with the reference architecture

## Verification

- `cargo check --package pp-editor-core`: PASSED
- `cargo check --workspace`: PASSED
- No external dependencies found on removed modules

## Rationale

These modules duplicated functionality now properly implemented in the `pp-editor-events` crate and used patterns incompatible with the reference-inspired architecture. Their removal eliminates technical debt and prevents confusion about the proper event handling approach.

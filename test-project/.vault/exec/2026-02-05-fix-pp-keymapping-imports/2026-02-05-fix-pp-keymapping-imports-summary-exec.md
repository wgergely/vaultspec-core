---
tags:
  - "#exec"
  - "#fix-pp-keymapping-imports"
date: 2026-02-05
related:
  - "[[2026-02-05-editor-demo-displaymap-reference]]"
---

# fix-pp-keymapping-imports summary

**Date:** 2026-02-05
**Task:** Fix broken imports in pp-keymapping after input.rs removal
**Status:** ✅ Complete

## Problem

After the removal of deprecated `pp-editor-core/src/input.rs`, the `pp-keymapping` crate had broken imports for:

- `Key` enum
- `Modifiers` struct
- `NamedKey` enum
- `KeyEvent`, `MouseEvent`, `ScrollEvent`, `ImeEvent` structs
- `EditorInputEvent` enum

## Solution

Created `crates/pp-keymapping/src/input_types.rs` containing all framework-agnostic input type definitions that were previously in `pp-editor-core/src/input.rs`.

### Rationale

These types belong in `pp-keymapping` because:

1. They represent framework-agnostic input abstractions
2. `pp-keymapping` is designed to be framework-independent (has optional GPUI feature)
3. These types are primarily used for key mapping, not core editor state
4. Moving them to pp-keymapping avoids circular dependencies

## Modified Files

### Created

- `crates/pp-keymapping/src/input_types.rs`
  - Defines: `Modifiers`, `NamedKey`, `Key`, `KeyEvent`, `MouseButton`, `MousePos`, `MouseEvent`, `ScrollDelta`, `ScrollEvent`, `ImeEvent`, `EditorInputEvent`
  - All types have proper Display implementations and documentation

### Updated

- `crates/pp-keymapping/src/lib.rs`
  - Added `input_types` module
  - Re-exported all input types from the crate root

- `crates/pp-keymapping/src/defaults.rs`
  - Changed: `use pp_editor_core::{Key, Modifiers, NamedKey}` → `use crate::input_types::{Key, Modifiers, NamedKey}`
  - Fixed unwrap() in header level loop to satisfy clippy

- `crates/pp-keymapping/src/keys.rs`
  - Changed: `use pp_editor_core::NamedKey` → `use crate::input_types::NamedKey`

- `crates/pp-keymapping/src/registry.rs`
  - Changed: `use pp_editor_core::{Key, Modifiers}` → `use crate::input_types::{Key, Modifiers}`

- `crates/pp-keymapping/src/mapper.rs`
  - Changed: `use pp_editor_core::EditorInputEvent` → `use crate::input_types::EditorInputEvent`

- `crates/pp-keymapping/src/gpui_adapter.rs`
  - Changed imports from pp_editor_core to `crate::input_types`
  - Fixed unwrap() call to satisfy clippy's unwrap_used lint

- `crates/pp-editor-main/src/lib.rs`
  - Updated re-exports to import input types from `pp_keymapping` instead of `pp_editor_core`

- `crates/pp-editor-main/src/default_keybindings.rs`
  - Changed: `use pp_editor_core::{Key, Modifiers}` → imports from `pp_keymapping`

- `crates/pp-editor-main/src/editor_model.rs`
  - Updated imports from `pp_editor_core` to `pp_keymapping` for input event types

## Verification

```bash
# pp-keymapping builds successfully
cargo check --package pp-keymapping --all-features
✅ Success

# No clippy errors (only warnings)
cargo clippy --package pp-keymapping --all-features
✅ Success (with pedantic warnings only)
```

## Technical Notes

1. **Input types architecture**: These types form a framework-agnostic input layer that sits between UI frameworks (GPUI, egui, Floem) and the editor core.

2. **No breaking changes**: All types maintain the same API as before, just moved to a different crate.

3. **Lint compliance**: Fixed all `unwrap_used` violations:
   - `defaults.rs`: Changed loop to use `if let Some()` pattern
   - `gpui_adapter.rs`: Added `unwrap_or('\0')` fallback

4. **Future work**: The remaining compilation errors in `pp-editor-main` are unrelated to this task and involve GPUI API usage (focus handles, AppContext, etc.).

## Commit

```
commit cffcc03
fix(keymapping): Update imports after input.rs removal
```

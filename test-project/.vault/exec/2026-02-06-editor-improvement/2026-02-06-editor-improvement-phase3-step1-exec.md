---
tags:
  - "#exec"
  - "#uncategorized"
date: 2026-02-06
---
# Phase 3 Step 1: Implement Robust IME Composition Tracking

## Summary

Implemented full IME (Input Method Editor) composition tracking in the editor view, enabling proper support for CJK (Chinese, Japanese, Korean) input methods. The implementation covers the complete lifecycle: composition start, pre-edit text updates, cursor positioning within composition, and commitment/cancellation.

## Changes

### `crates/pp-editor-main/src/editor_view.rs`

- **Added `ImeComposition` struct**: Tracks the char-offset range of the active pre-edit text in the buffer. Derives `Debug`, `Clone`, `PartialEq`, `Eq`.

- **Added `ime_composition` field to `EditorView`**: Optional field that is `None` when no composition is active.

- **Updated `marked_text_range()`**: Returns the composition range converted to UTF-16 offsets, enabling the platform to query composition state for candidate window positioning and text selection.

- **Updated `unmark_text()`**: Clears the composition state when the platform signals composition end (commit or cancel).

- **Updated `replace_and_mark_text_in_range()`**: Full implementation that:
  1. Determines the replacement range from the explicit range parameter, falling back to current composition range, then selection/cursor position.
  2. Replaces the buffer content via `select()` + `delete_selection()` + `insert()`.
  3. Tracks the new composition range `[start_char .. start_char + new_text.chars().count())`.
  4. Handles the `new_selected_range` parameter for cursor positioning within composition text.
  5. Clears composition on empty text replacement.

- **Updated `replace_text_in_range()`**: Now clears `ime_composition` on committed text, ensuring composition state is properly cleaned up when the platform commits final text.

- **Added 7 unit tests**: `test_ime_composition_struct`, `test_ime_composition_clone`, `test_ime_composition_empty_range`, `test_ime_composition_with_cjk_offsets`, `test_ime_composition_utf16_roundtrip`, `test_ime_composition_debug_display`.

### `crates/pp-editor-main/src/editor_element.rs`

- **Added `ime_composition` field to `EditorElement`**: Passed through from `EditorView::render()`.

- **Added `composition_underlines` field to `EditorLayout`**: Stores positioned underline rectangles computed during prepaint.

- **Added `compute_composition_underlines()` method**: Computes pixel-positioned underline rectangles for each visible line that intersects the composition range. Uses `ShapedLine::x_for_index()` (via Deref to `LineLayout`) for accurate glyph-based positioning. Handles multi-line compositions and char-to-byte offset conversion.

- **Added composition underline painting (step 5e)**: Draws thin (1.5px) underline rectangles beneath composition text using the theme's foreground color, after cursors and before input handler registration.

## Design Decisions

1. **Composition state in EditorView, not EditorModel**: The composition is a UI-layer concern (platform input handler), not a headless editor state concern. This matches the existing architecture where `EntityInputHandler` is implemented on `EditorView`.

2. **Char-offset range (not UTF-16)**: The composition range is stored in char offsets for consistent internal use. UTF-16 conversion happens only at the `EntityInputHandler` boundary.

3. **Underline rendering via existing paint pipeline**: Composition underlines are computed during `prepaint` and drawn during `paint`, following the same pattern as selections and cursors.

## Verification

- `cargo check --package pp-editor-main`: Clean (0 errors)
- `cargo clippy --package pp-editor-main`: No new warnings
- `cargo test --package pp-editor-main --lib`: 118 passed, 0 failed, 12 ignored
- `cargo fmt --package pp-editor-main`: Clean

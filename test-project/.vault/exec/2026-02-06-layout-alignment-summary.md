---
tags:
  - "#exec"
  - "#layout-alignment"
date: 2026-02-06
related:
  - "[[2026-02-06-editor-improvement-plan]]"
---

# layout-alignment summary

**Date:** 2026-02-06
**Status:** COMPLETE

## Goal

Align the editor implementation with the Z reference architecture by integrating the proper text layout engine into the logical layer (`EditorState`, `DisplayMap`) and the interaction layer (`EditorView` input handling). This resolves the critical "visual lie" where rendered text (using GPUI) and logical text (using naive approximation) were disconnected, preventing accurate cursor positioning and input handling.

## Assessment Findings

1. **Rendering vs. Logic Mismatch**: `EditorElement` was correctly using `gpui::TextSystem` to render shaped text (variable width, ligatures), but `EditorView`'s input handling and cursor positioning relied on a hardcoded `font_size * 0.6` constant (monospaced assumption).
2. **Missing Sync**: `EditorState` had a `DisplayMap`, but it was never synchronized with a layout engine, so `WrapMap` (soft wrapping) had no way to function.
3. **Unused GpuiTextLayout**: The `GpuiTextLayout` struct existed in `pp-ui-core` but was not used by the main editor crate.

## Implemented Changes

### 1. Core State Refactoring

- **Modified `pp-editor-core/src/state.rs`**: Added `sync_layout` method to `EditorState` to allow pushing layout metrics (font, wrap width) into the `DisplayMap`.

### 2. Main Editor Integration

- **Updated `pp-editor-main/Cargo.toml`**: Enabled the `gpui` feature for `pp-ui-core` dependency.
- **Refactored `pp-editor-main/src/editor_model.rs`**:
  - Added `Arc<GpuiTextLayout>` ownership to `EditorModel`.
  - Initialized layout engine with the window's `TextSystem`.
  - Added `update_layout()` to propagate layout and wrapping settings to `EditorState`.
  - Ensured layout updates on text mutations (`handle_input`, `resize_block`).

### 3. View & Interaction Alignment

- **Updated `pp-editor-main/src/editor_view.rs`**:
  - Replaced naive `char_width` calculations with `layout.char_position()` and `layout.index_at_position()`.
  - Updated `calculate_cursor_visual_static`, `calculate_selection_rects_static`, `bounds_for_range`, and `character_index_for_point` to use the accurate layout engine.
  - Removed broken/unused instance accessor methods.

## Result

The editor now uses the same high-fidelity text layout engine for both painting pixels and calculating cursor positions/hit boxes. This creates a solid foundation for:

- Accurate keyboard navigation (even with variable width fonts).
- Precise mouse selection and cursor placement.
- Correct soft wrapping (via `WrapMap` synchronization).

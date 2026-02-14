---
feature: editor-improvement
phase: phase3
step: 3
date: 2026-02-06
title: Implement editor gutter rendering
status: complete
files_changed:
  - crates/pp-editor-main/src/gutter.rs
  - crates/pp-editor-main/src/editor_element.rs
  - crates/pp-editor-main/src/editor_model.rs
  - crates/pp-editor-main/src/editor_view.rs
  - crates/pp-editor-main/src/lib.rs
tests_added: 14
tests_passing: 145
---

# Phase 3 Step 3: Implement Editor Gutter Rendering

## Summary

Enhanced the editor gutter with current line highlighting, a gutter decoration system (breakpoints, diagnostics, custom markers), and proper data flow from model to paint pipeline. The existing gutter infrastructure (background, separator, line numbers, hitbox-based click-to-select) was already functional; this step adds the missing visual features.

## Changes

### `crates/pp-editor-main/src/gutter.rs`

- **Added `DiagnosticSeverity` enum**: Error, Warning, Info, Hint -- used for diagnostic gutter markers with severity-appropriate colors.

- **Added `GutterDecoration` enum**: Three variants:
  - `Breakpoint { active: bool }` -- filled circle (active) or outline (disabled)
  - `Diagnostic { severity: DiagnosticSeverity }` -- colored dot based on severity
  - `Custom { color: Color, label: Option<String> }` -- caller-provided marker

- **Added `GutterDecorations` storage**: `BTreeMap<usize, Vec<GutterDecoration>>` keyed by buffer line (0-based). BTreeMap ensures iteration in line order for efficient rendering. Provides `add()`, `clear_line()`, `clear_all()`, `get()`, `iter()`, `is_empty()`, `len()`.

- **Added 14 unit tests**: Coverage for `DiagnosticSeverity` equality, `GutterDecoration` variants (breakpoint, diagnostic, custom with/without label), and `GutterDecorations` storage (empty, add, multiple per line, multiple lines, get empty, clear line, clear all, iteration order, clone).

### `crates/pp-editor-main/src/editor_model.rs`

- **Added `gutter_decorations: GutterDecorations` field**: Stores decoration state alongside other editor model state.

- **Added accessor methods**: `gutter_decorations()`, `gutter_decorations_mut()`, `add_gutter_decoration(line, decoration)`.

- **Updated constructors**: Both `new()` and `from_text()` initialize `gutter_decorations: GutterDecorations::new()`.

### `crates/pp-editor-main/src/editor_element.rs`

- **Added `PositionedGutterDecoration` struct**: Holds center point, radius, and decoration data for a positioned marker ready for painting.

- **Added `gutter_decorations` field to `EditorElement`**: Passed through from EditorView render.

- **Added `compute_gutter_decorations()` method**: During prepaint, maps buffer-line decorations to pixel-positioned markers. Each marker is centered vertically on its line, positioned in the left margin of the gutter.

- **Added `gutter_decoration_items` field to `EditorLayout`**: Stores positioned decorations for the paint phase.

- **Added current line highlight painting (step 1b)**: Uses `theme.gutter.current_line_bg` to paint a highlight rectangle behind the current line's gutter row. The `current_line` index was already tracked in `EditorLayout` but never consumed.

- **Added `paint_gutter_decorations()` method**: Paints markers as rounded quads (circles via `corner_radii(radius)`). Breakpoints use red fill/outline, diagnostics use severity-mapped colors (red/yellow/blue/gray), custom decorations use caller-provided color.

### `crates/pp-editor-main/src/editor_view.rs`

- **Updated `Render::render()`**: Snapshots `gutter_decorations` from the model and passes to `EditorElement::new()`.

### `crates/pp-editor-main/src/lib.rs`

- **Updated public re-exports**: Added `DiagnosticSeverity`, `GutterDecoration`, `GutterDecorations` to the public API.

## Design Decisions

1. **BTreeMap for decoration storage**: Ensures decorations are iterated in line order during the paint pass, avoiding a sort step. Also allows efficient range queries if needed for visible-only filtering in the future.

2. **Decorations in EditorModel, not EditorState**: Gutter decorations (breakpoints, diagnostics) are a UI-layer concern driven by external tools (debugger, LSP). They don't belong in the headless `EditorState` which is framework-agnostic.

3. **Rounded quads for markers**: GPUI's `PaintQuad` supports `corner_radii`. Setting radius = diameter/2 creates perfect circles. This avoids needing a separate circle primitive.

4. **Current line highlight before separator**: The highlight is painted after the gutter background but before the separator and line numbers, so it provides a subtle background tint without occluding the separator or text.

## Verification

- `cargo check --package pp-editor-main --all-targets`: Clean
- `cargo clippy --package pp-editor-main --all-targets`: No new warnings
- `cargo test --package pp-editor-main --lib`: 133 passed, 0 failed, 12 ignored
- `cargo test --package pp-editor-main --lib gutter`: 30 passed (16 existing + 14 new)
- `cargo fmt --package pp-editor-main`: Clean

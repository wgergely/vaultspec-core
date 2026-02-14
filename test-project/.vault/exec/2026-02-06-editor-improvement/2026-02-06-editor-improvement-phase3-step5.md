---
feature: editor-improvement
date: 2026-02-06
phase: 3
step: 5
status: completed
related:
  - "[[2026-02-06-editor-improvement-phase3-step4]]"
---

# Phase 3, Step 5: Refine EditorView Input Handling

## Objective

Review and fix input handling inconsistencies. Wire missing keyboard shortcuts. Add scroll wheel support.

## Changes

### editor_model.rs — SelectUp/SelectDown fix

- **Bug**: `SelectUp` and `SelectDown` previously called `move_up()`/`move_down()` which moves the cursor without extending selection. This broke Shift+Up/Down selection.
- **Fix**: Compute target position using buffer line/column arithmetic, then call `select_to(target)` to properly extend the selection.

### editor_model.rs — Fold keyboard shortcuts

- Added `FoldRegion`, `UnfoldRegion`, `FoldAll`, `UnfoldAll` to the `dispatch_action` match arms.
- `FoldRegion` (Ctrl+Shift+[): folds the region at the current cursor line.
- `UnfoldRegion` (Ctrl+Shift+]): unfolds the region at the current cursor line.
- `FoldAll` (Ctrl+0): collapses all fold regions.
- `UnfoldAll` (Ctrl+9): expands all fold regions.
- These keybindings were already registered in `pp-keymapping::defaults` but never dispatched.

### editor_element.rs — Scroll wheel handler

- Added `ScrollWheelEvent` import from GPUI.
- Added scroll wheel event handler in `paint_mouse_listeners`:
  - Converts `ScrollDelta` (pixel or line-based) to pixel deltas using `pixel_delta(line_height)`.
  - Updates `viewport.scroll_y` and `viewport.scroll_x` with clamping to `>= 0.0`.
- Cloned model handle before move closures to avoid ownership conflict with the drag handler.

## Tests

- All 151 existing tests pass (0 failures, 12 ignored).
- No new tests added for this step (keyboard shortcuts and scroll wheel require GPUI AppContext for integration testing, which is gated behind `todo_gpui_tests`).

## Verification

- `cargo check --package pp-editor-main --all-targets`: pass
- `cargo test --package pp-editor-main`: 151 passed, 0 failed
- `cargo fmt`: clean

## Commit

`25331cf` — fix: refine EditorView input handling - SelectUp/Down, fold shortcuts, scroll wheel

---
feature: editor-improvement
date: 2026-02-06
phase: 3
step: 4
status: completed
related:
  - "[[2026-02-06-editor-improvement-phase3-step3]]"
---

# Phase 3, Step 4: Code Folding Implementation

## Objective

Implement code folding with FoldMap synchronization, gutter fold indicators, and indentation-based fold region detection.

## Changes

### pp-editor-core (fold_map.rs)

- Added `unfold(start_row, end_row)` method to `FoldMap` — rebuilds SumTree converting Folded items overlapping the range back to Neutral, merges adjacent Neutral items
- Added `unfold_all()` method — replaces entire tree with single Neutral item

### pp-editor-main (folding.rs)

- Added `fold_at(start)` / `unfold_at(start)` — targeted fold/unfold
- Added `fold_all()` / `unfold_all()` — bulk operations
- Added `fold_at_line(line)` — find fold containing a buffer line
- Added `set_folds(folds)` — replace all fold regions
- Added `detect_indentation_folds(lines)` — indentation-based fold region detection (handles blank lines within folds)
- Added `sync_to_fold_map(fold_map, total_rows)` — bridge between FoldingSystem and FoldMap; resets and applies all collapsed folds

### pp-editor-main (editor_model.rs)

- Added fold action methods: `fold_at_line()`, `unfold_at_line()`, `toggle_fold_at_line()`, `fold_all()`, `unfold_all()`, `detect_folds()`, `sync_folds()`
- `sync_folds()` calls `sync_to_fold_map()` then `update_layout()`

### pp-editor-main (editor_view.rs)

- Added `has_fold` and `is_collapsed` fields to `RenderLine`
- Updated `prepare_render_items_static` to populate fold info from `model.folding().folds()`

### pp-editor-main (editor_element.rs)

- Added `FoldIndicator` struct and `fold_indicators` field to `EditorLayout`
- Added `compute_fold_indicators()` in prepaint — positions indicators for foldable lines
- Added `paint_fold_indicators()` in paint (step 3c) — collapsed = filled quad, expanded = outline quad using `theme.gutter.fold_indicator` color
- Updated all test RenderLine constructions with `has_fold: false, is_collapsed: false`

## Tests Added (18 new)

### folding.rs tests

- `test_fold_at_and_unfold_at` — targeted fold/unfold operations
- `test_fold_at_nonexistent_is_noop` — no-op when fold doesn't exist
- `test_fold_all_and_unfold_all` — bulk operations
- `test_fold_at_line_finds_containing_fold` — lookup by buffer line
- `test_set_folds_replaces_all` — replace fold set
- `test_set_folds_rejects_invalid` — rejects start >= end
- `test_detect_indentation_folds_basic` — single fold region
- `test_detect_indentation_folds_nested` — nested fold regions
- `test_detect_indentation_folds_blank_lines` — blank lines don't break folds
- `test_detect_indentation_folds_empty` — empty input
- `test_detect_indentation_folds_single_line` — single line (no folds)
- `test_sync_to_fold_map` — fold sync with FoldMap coordinate verification
- `test_sync_to_fold_map_unfold` — unfold sync restores identity mapping
- `test_visual_line_count` — correct count with collapsed folds
- `test_multiple_collapsed_folds` — multiple simultaneous collapsed folds

### editor_element.rs tests

- `test_fold_indicator_computed_for_foldable_line` — expanded fold indicator
- `test_fold_indicator_collapsed_state` — collapsed fold indicator
- `test_no_fold_indicators_when_no_folds` — no indicators for plain lines

## Verification

- `cargo check --package pp-editor-main --all-targets`: pass
- `cargo test --package pp-editor-main`: 151 passed, 0 failed, 12 ignored
- `cargo test --package pp-editor-core`: 420 passed, 0 failed
- `cargo fmt`: clean
- `cargo clippy`: 0 new errors (11 pre-existing from other modules)

## Commit

`baa1f30` — feat: implement code folding with FoldMap sync, gutter indicators, and indentation detection

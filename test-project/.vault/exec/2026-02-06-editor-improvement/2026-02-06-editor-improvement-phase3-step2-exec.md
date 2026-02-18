---
tags:
  - "#exec"
  - "#uncategorized"
date: 2026-02-06
---
# Phase 3 Step 2: Implement Custom Block Layout Sync with BlockMap

## Summary

Connected the GPUI element measurement pipeline to the BlockMap coordinate system so that dynamically-sized custom blocks (markdown previews, images, etc.) automatically synchronize their rendered height with the DisplayMap. This resolves the block height feedback loop: render -> measure -> compare -> resize -> re-render.

## Changes

### `crates/pp-editor-core/src/display_map/block_map.rs`

- **Added `block_height()` query method**: Traverses the SumTree to find a block by ID and returns its stored height. Returns `None` if the block is not found. Handles both `BlockItem::Block` and `BlockItem::Replace` variants.

- **Added `test_block_height_query` test**: Validates height query for Above and Replace blocks, verifies `None` for non-existent IDs, and confirms height updates after resize.

### `crates/pp-editor-main/src/editor_view.rs`

- **Updated `prepare_render_items_static()`**: After measuring each block element with `layout_as_root()`, the measured pixel height is converted to display rows (`ceil(px / line_height)`) and compared against the stored height via `block_map.block_height(id)`. Mismatches are recorded in the `resized_blocks` HashMap (was previously unused).

- **Updated resize feedback loop in `Render::render()`**: Changed from individual `resize_block()` calls to batch `resize_blocks()` via `DisplayMap`, which performs a single SumTree rebuild regardless of how many blocks changed. Only calls `update_layout()` if at least one block actually changed height.

## Design Decisions

1. **Height in display rows, not pixels**: BlockMap tracks height in abstract "display rows", not pixels. The conversion `ceil(actual_px / line_height)` ensures blocks always occupy at least 1 display row and round up to prevent content clipping.

2. **Deferred resize via `cx.defer()`**: Resizes are applied after the current render completes to avoid mutating state during the paint pipeline. This matches GPUI's reactive model.

3. **Batch resize**: Using `resize_blocks()` (backed by `resize_batch()`) avoids O(n*k) SumTree rebuilds when k blocks change simultaneously.

## Verification

- `cargo check --package pp-editor-main`: Clean
- `cargo test --package pp-editor-core --lib block_map`: 16 passed
- `cargo test --package pp-editor-main --lib`: 118 passed, 0 failed
- No new clippy warnings

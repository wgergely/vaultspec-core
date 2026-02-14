---
tags:
  - "#plan"
  - "#editor-demo"
date: 2026-02-05
related:
  - "[[2026-02-05-editor-demo-architecture]]"
  - "[[2026-02-05-editor-demo-research]]"
  - "[[2026-02-05-editor-demo-displaymap-reference]]"
  - "[[2026-02-05-editor-demo-core-reference]]"
  - "[[2026-02-04-displaymap-reference]]"
  - "[[2026-02-04-implement-zed-displaymap]]"
---

# Editor Demo Phase 3 Plan: Display Map Completeness

Complete the transform pipeline. Implement InlayMap and TabMap pass-throughs, wire `DisplayMap::sync()` to call all layers, and add `BlockPlacement::Replace` for future markdown live preview. This phase converts the display map from a partially-connected pipeline into a fully-wired coordinate transformation system.

## Proposed Changes

The display map pipeline is at 32% alignment with Zed ([[2026-02-05-editor-demo-displaymap-reference]] Section 11). The layer ordering is correct (Inlay -> Fold -> Tab -> Wrap -> Block), FoldMap/WrapMap/BlockMap use SumTree correctly, but two layers are completely empty stubs and the sync chain is broken:

1. **InlayMap is an empty stub.** The file `crates/pp-editor-core/src/display_map/inlay_map.rs` contains only a 13-line empty struct with `new()`. No coordinate mapping methods exist. The `DisplayMap::to_display_point()` currently bypasses InlayMap by constructing `InlayPoint::new(point.row, point.column)` directly from `BufferPoint` -- this is coincidentally correct for a pass-through but fragile ([[2026-02-05-editor-demo-displaymap-reference]] Section 1).

2. **TabMap is an empty stub.** The file `crates/pp-editor-core/src/display_map/tab_map.rs` contains only a 13-line empty struct with `new()`. Hard tab characters (`\t`) are not expanded -- they display as single-width characters. The `DisplayMap::to_display_point()` bypasses TabMap by copying FoldPoint coordinates directly to TabPoint ([[2026-02-05-editor-demo-displaymap-reference]] Section 1).

3. **DisplayMap::sync() only calls WrapMap.** The current `sync()` method at line 153-168 of `crates/pp-editor-core/src/display_map/mod.rs` only calls `self.wrap_map.sync(lines, layout, wrap_width)`. InlayMap, FoldMap, TabMap, and BlockMap are never synced on text changes.

4. **BlockPlacement only supports Above/Below.** The enum at `crates/pp-editor-core/src/display_map/block_map.rs:14-19` has two variants. `Replace(RangeInclusive<T>)` is needed for markdown live preview where source syntax is hidden and replaced with rendered content ([[2026-02-05-editor-demo-displaymap-reference]] Section 7).

## Tasks

1. **Implement InlayMap pass-through**

   - Step summary: `.docs/exec/2026-02-05-editor-demo/2026-02-05-editor-demo-phase3-step1.md`
   - Executing sub-agent: standard-executor
   - References: [[2026-02-05-editor-demo-displaymap-reference]] Section 1, [[2026-02-05-editor-demo-architecture]] Phase 3 Task 1

   Sub-steps:
   1. Add coordinate mapping methods to `InlayMap`:
      - `to_inlay_point(buffer: BufferPoint) -> InlayPoint`: Pure identity -- returns `InlayPoint::new(buffer.row, buffer.column)`.
      - `from_inlay_point(inlay: InlayPoint) -> BufferPoint`: Pure identity -- returns `BufferPoint::new(inlay.row, inlay.column)`.
   2. Add a `sync(&mut self, buffer_line_count: u32)` method that accepts the buffer line count. For the pass-through implementation this is a no-op but establishes the sync interface for future inlay hint support.
   3. Add a `row_count(&self) -> u32` method that returns the total row count. For pass-through, this equals the buffer line count stored during sync.
   4. Store `buffer_line_count: u32` as a field on `InlayMap`, updated during `sync()`.
   5. Update `DisplayMap::to_display_point()` to call `self.inlay_map.to_inlay_point(point)` instead of directly constructing `InlayPoint`.
   6. Update `DisplayMap::from_display_point()` to call `self.inlay_map.from_inlay_point(inlay_point)` instead of directly constructing `BufferPoint`.
   7. Add unit tests: identity mapping round-trip, sync updates row count.

2. **Implement TabMap with tab expansion**

   - Step summary: `.docs/exec/2026-02-05-editor-demo/2026-02-05-editor-demo-phase3-step2.md`
   - Executing sub-agent: standard-executor
   - References: [[2026-02-05-editor-demo-displaymap-reference]] Section 1, [[2026-02-05-editor-demo-architecture]] Phase 3 Task 2

   Sub-steps:
   1. Add a `tab_size: u32` field to `TabMap` (default 4). Add a constructor `TabMap::with_tab_size(tab_size: u32)`.
   2. Add `to_tab_point(fold: FoldPoint, line_text: &str) -> TabPoint`: Expand column position by replacing each tab character with spaces up to the next tab stop. Tab stops are at column positions that are multiples of `tab_size`. The algorithm: iterate characters in the line up to `fold.column`, tracking the visual column. For each `\t`, advance to the next tab stop. Return `TabPoint::new(fold.row, visual_column)`.
   3. Add `from_tab_point(tab: TabPoint, line_text: &str) -> FoldPoint`: Reverse the expansion -- iterate characters tracking visual column until it reaches `tab.column`, return the character offset as `FoldPoint`. Handle the case where `tab.column` falls within a tab expansion (snap to the tab character position).
   4. Add a `sync(&mut self, fold_line_count: u32, tab_size: u32)` method to update the stored tab_size and line count.
   5. Add a `row_count(&self) -> u32` method. TabMap does not change row count (tabs do not introduce new rows), so this equals the fold line count.
   6. The tab expansion needs access to line text. Either: (a) pass a line-text accessor to the mapping methods, or (b) store the fold-output lines during sync. Option (a) is simpler for the demo and avoids duplicating text storage. Update `DisplayMap::to_display_point()` and `from_display_point()` to pass the relevant line text to TabMap methods. This requires access to the buffer text (via `EditorState` or a text accessor).
   7. For the initial implementation, if accessing line text is too complex in the current architecture, implement TabMap as a pure pass-through (identity) with a TODO for tab expansion. The critical deliverable is the sync interface and coordinate methods existing, even if tab expansion is deferred.
   8. Add unit tests: tab expansion at various positions, round-trip mapping, tab_size configuration.

3. **Wire DisplayMap::sync() to call all layers**

   - Step summary: `.docs/exec/2026-02-05-editor-demo/2026-02-05-editor-demo-phase3-step3.md`
   - Executing sub-agent: standard-executor
   - References: [[2026-02-05-editor-demo-displaymap-reference]] Section 5, [[2026-02-05-editor-demo-architecture]] Phase 3 Task 3

   Sub-steps:
   1. Refactor `DisplayMap::sync()` signature to accept all needed parameters: `&mut self, lines: &[String], layout: &dyn TextLayout, wrap_width: f32, tab_size: u32`. The `tab_size` parameter is new.
   2. Add InlayMap sync call: `self.inlay_map.sync(lines.len() as u32)`. This is first in the chain.
   3. Add FoldMap awareness: the FoldMap is currently synced externally (folds are set by user action, not by text changes). Verify that `DisplayMap::sync()` does not discard fold state. If folds reference buffer rows that have been deleted, the fold state should be cleaned up. For the demo, a simple bounds check is sufficient.
   4. Add TabMap sync call: `self.tab_map.sync(fold_row_count, tab_size)` where `fold_row_count` comes from the FoldMap (number of visual rows after folding).
   5. Keep the existing WrapMap sync call: `self.wrap_map.sync(lines, layout, wrap_width)`. Note: WrapMap currently receives raw buffer lines. For correctness it should receive fold-output lines (lines after folding). For the demo with small files and no active folds, this discrepancy is acceptable. Add a TODO comment noting that WrapMap should receive post-fold lines.
   6. Add BlockMap awareness: BlockMap does not need a sync call for text changes (blocks are positioned by buffer row anchors), but verify that `block_map.row_count()` returns correct values after the other layers update.
   7. Update `DisplayMap::row_count()` to correctly chain through all layers: `inlay_rows -> fold_rows -> tab_rows -> wrap_rows -> block_rows`.
   8. Add integration tests: sync after text insertion preserves fold state, sync updates all layer row counts, coordinate mapping round-trips through all layers.

4. **Add BlockPlacement::Replace variant**

   - Step summary: `.docs/exec/2026-02-05-editor-demo/2026-02-05-editor-demo-phase3-step4.md`
   - Executing sub-agent: standard-executor
   - References: [[2026-02-05-editor-demo-displaymap-reference]] Section 7, [[2026-02-05-editor-demo-architecture]] Phase 3 Task 4

   Sub-steps:
   1. Add a `Replace` variant to `BlockPlacement` in `crates/pp-editor-core/src/display_map/block_map.rs`:

      ```
      Replace {
          start_row: u32,
          end_row: u32,  // inclusive
      }
      ```

      This replaces a range of buffer rows with the block content. The start_row and end_row are buffer row indices.
   2. Update `BlockItem::Block` to support the `Replace` placement. When a Replace block is present, the rows in `start_row..=end_row` are hidden and replaced by a single block row of `height` display rows.
   3. Update `BlockMap::rebuild()` (the SumTree rebuild method) to handle Replace blocks. When processing the sorted block list, a Replace block should: (a) emit a Neutral item for rows before `start_row`, (b) skip `(end_row - start_row + 1)` buffer rows, (c) emit the Block item with the specified display height.
   4. Update `BlockMap::to_display_point()` to handle Replace blocks. When a buffer point falls within a replaced range, map it to the display row of the replacement block.
   5. Update `BlockMap::from_display_point()` to handle Replace blocks. When a display point corresponds to a Replace block, return the start_row of the replaced range (the block "represents" all replaced rows).
   6. Update `BlockSummary` to correctly account for Replace blocks: `buffer_rows` should include the replaced rows, `display_rows` should include the block height but not the replaced rows.
   7. Update `BlockMap::insert_block()` and any existing block management methods to accept `Replace` placement.
   8. Add unit tests: Replace block hides correct rows, display point mapping through Replace blocks, inserting multiple Replace blocks (non-overlapping), row count with Replace blocks.
   9. Do NOT implement the render closure integration for Replace blocks in this phase. The block rendering system from Phase 1 already handles painting blocks via `CustomBlock`. The Replace variant only affects coordinate mapping in the BlockMap layer.

## Parallelization

- **Tasks 1 and 2 can proceed in parallel.** InlayMap and TabMap are independent layers with no shared code. They both need changes to `DisplayMap::to_display_point()` and `from_display_point()`, but these changes are to separate sections of those methods (InlayMap is the first transform, TabMap is the third).
- **Task 3 depends on Tasks 1 and 2.** Wiring `sync()` requires the sync interfaces defined in Tasks 1 and 2.
- **Task 4 (BlockPlacement::Replace) is independent of Tasks 1-3.** It modifies only `block_map.rs` and can proceed in parallel with all other tasks.

Execution order: `(1 | 2 | 4) -> 3`

## Verification

### Success Criteria

1. **InlayMap pass-through is transparent.** Coordinate mapping through the full pipeline (Buffer -> Display -> Buffer) produces identical results with the InlayMap layer active. All existing tests that test `DisplayMap::to_display_point()` and `from_display_point()` continue to pass.
2. **TabMap handles tab characters.** If tab expansion is implemented: a buffer line containing `\tHello` with tab_size=4 maps column 0 (the tab) to display columns 0-3, and `H` maps to display column 4. If tab expansion is deferred (pass-through): the sync interface and coordinate methods exist and pass identity tests.
3. **DisplayMap::sync() calls all layers.** After calling `sync()`, all layers have updated state. Verifiable by checking row counts: `inlay_map.row_count()`, `tab_map.row_count()` (if applicable), `wrap_map.row_count()`, `block_map.row_count()` all return correct values.
4. **Full-pipeline coordinate round-trip works.** `from_display_point(to_display_point(bp))` returns `bp` for any valid buffer point (within buffer bounds), with or without folds active.
5. **BlockPlacement::Replace hides rows.** Inserting a Replace block for rows 5-10 with height 2 means: (a) display rows for lines 5-10 are removed, (b) 2 display rows for the block are inserted, (c) total display rows decrease by `(10-5+1) - 2 = 4`, (d) display points after the block are offset by -4 rows.
6. **No regressions in existing block/fold/wrap tests.** Existing Above/Below blocks still work correctly. Fold coordinate mapping still works. Wrap coordinate mapping still works.
7. **`cargo check --all-targets` passes** for `pp-editor-core`.
8. **`cargo test -p pp-editor-core` passes** with all new and existing tests.

### Verification Method

- Run `cargo test -p pp-editor-core` to validate all display map layer tests.
- Write property-based tests for coordinate round-trips: for random buffer points, verify `from_display_point(to_display_point(bp)) == bp`.
- Write integration tests that exercise the full pipeline with folds + blocks simultaneously.
- The Replace block test should verify the row arithmetic with a concrete example: 20 buffer lines, one Replace block covering rows 5-10 (6 rows) with height 2, expected total display rows = 20 - 6 + 2 = 16.
- Visual verification via `cargo run --example demo -p pp-editor-main` confirms that tab characters (if implemented) display at correct widths and that folds still render correctly.

---
tags:
  - "#plan"
  - "#displaymap-integration"
date: 2026-02-04
related: "[[2026-02-04-adopt-zed-displaymap]]"
---

# Plan: DisplayMap Integration & Optimization

Date: 2026-02-04
Task: DisplayMap Integration & Optimization
Exec summary: `.docs/exec/2026-02-04-displaymap-integration/summary.md`

## Brief

Integrate the newly created `DisplayMap` into the core editor architecture and refactor its internal data structures (`BlockMap`, `WrapMap`) to use `SumTree` for O(log N) performance. This enables high-performance "Live Preview" (block rendering) and correct soft-wrapping handling in the View layer.

## Goals

- Refactor `BlockMap` to use `SumTree` instead of `Vec<Block>` to resolve O(N) performance bottleneck.
- Refactor `WrapMap` to use `SumTree` for efficient line wrapping lookups.
- Integrate `DisplayMap` into `EditorState` (core) and ensure it stays synchronized with buffer edits.
- Update `EditorView` (main) to render using `DisplayMap` coordinates, effectively enabling "Block" rendering.

## Success Criteria

- `BlockMap` uses `SumTree` internally; tests pass.
- `WrapMap` uses `SumTree` internally; tests pass.
- `EditorState` owns a `DisplayMap` instance.
- Text insertion/deletion in `EditorState` correctly updates `DisplayMap`.
- `EditorView` renders "Blocks" (virtual vertical space) as defined in `BlockMap`.
- Scrolling and cursor movement respect `DisplayMap` coordinates (e.g. skipping over blocks or soft wraps).

# Steps

- Phase 1: Optimization (SumTree Refactor) - (audit file not found) **COMPLETED**
  - Name: Refactor BlockMap to SumTree
  - Step summary: `.docs/exec/2026-02-04-displaymap-integration/01-refactor-blockmap.md`
  - Executing sub-agent: rust-executor-complex
  - References: [[pp-editor-core-sum-tree]] **COMPLETED**
  - Instructions:
    - Define `BlockItem` and `BlockSummary` in `block_map.rs`.
    - Replace `Vec<Block>` with `SumTree<BlockItem>`.
    - Re-implement `to_display_point` and `from_display_point` using `cursor.seek`.
    - Ensure existing tests in `block_map.rs` pass.

  - Name: Refactor WrapMap to SumTree
  - Step summary: `.docs/exec/2026-02-04-displaymap-integration/02-refactor-wrapmap.md`
  - Executing sub-agent: rust-executor-complex
  - References: [[pp-editor-core-sum-tree]]
  - Instructions:
    - Define `WrapItem` and `WrapSummary`.
    - Replace `Vec<Vec<u32>>` with `SumTree<WrapItem>`.
    - Implement `to_wrap_point` and `from_wrap_point` using cursors.
    - Note: This is complex; if full SumTree is too much, at least flatten the nested Vec structure, but SumTree is preferred per audit.

- Phase 2: Integration (Editor Core) - @crates/pp-editor-core/src/state.rs
  - Name: Add DisplayMap to EditorState
  - Step summary: `.docs/exec/2026-02-04-displaymap-integration/03-integrate-editor-state.md`
  - Executing sub-agent: rust-executor-standard
  - References: [[pp-editor-core-display-map]] **COMPLETED**
  - Instructions:
    - Add `display_map: DisplayMap` to `EditorState` struct.
    - Initialize it in `EditorState::new` and `from_text`.
    - In `EditorState::insert` and `delete_...`, call `self.display_map.handle_operation(...)` (you may need to implement this method on `DisplayMap` to dispatch to sub-maps).
    - Ensure `DisplayMap` stays in sync with `Buffer` version.

- Phase 3: Rendering (Editor View) - [[pp-editor-main-editor-view]]
  - Name: DisplayMap Rendering Logic
  - Step summary: `.docs/exec/2026-02-04-displaymap-integration/04-render-blocks.md`
  - Executing sub-agent: rust-executor-standard
  - References: [[pp-editor-core-block-map]] **COMPLETED**
  - Instructions:
    - Update `EditorView::prepare_render_lines` to use `DisplayMap`'s iterator (you might need to create a `display_lines()` iterator on `DisplayMap`).
    - The iterator should yield either `TextLine` or `Block`.
    - Render `Block` items as empty vertical space (or placeholders) for now, with correct height.
    - Ensure the visual Y position calculation accounts for Blocks.

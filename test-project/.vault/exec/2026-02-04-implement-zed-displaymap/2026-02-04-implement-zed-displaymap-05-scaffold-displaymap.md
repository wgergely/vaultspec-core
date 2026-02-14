---
tags:
  - "#exec"
  - "#implement-zed-displaymap"
date: 2026-02-04
related:
  - "[[2026-02-04-implement-zed-displaymap-plan]]"
---

# implement-zed-displaymap

Date: 2026-02-04
Task: Scaffold DisplayMap Structure
Status: Completed

## Changes

- Created `display_map` module in `pp-editor-core`.
- Defined `BufferPoint` and `DisplayPoint` types in `display_map/mod.rs`.
- Scaffolded the layered map structure:
  - `InlayMap`: Virtual text insertions.
  - `FoldMap`: Code folding.
  - `TabMap`: Tab expansion.
  - `WrapMap`: Soft wrapping.
  - `BlockMap`: Block-level elements.
- Integrated `DisplayMap` into `pp-editor-core` and re-exported key types.
- Verified that the codebase compiles with the new module.

## Files Created/Modified

- `crates/pp-editor-core/src/display_map/mod.rs`
- `crates/pp-editor-core/src/display_map/inlay_map.rs`
- `crates/pp-editor-core/src/display_map/fold_map.rs`
- `crates/pp-editor-core/src/display_map/tab_map.rs`
- `crates/pp-editor-core/src/display_map/wrap_map.rs`
- `crates/pp-editor-core/src/display_map/block_map.rs`
- `crates/pp-editor-core/src/lib.rs` (re-exports)

## Next Steps

- Implement `BlockMap` logic to handle virtual blocks for Markdown Live Preview.

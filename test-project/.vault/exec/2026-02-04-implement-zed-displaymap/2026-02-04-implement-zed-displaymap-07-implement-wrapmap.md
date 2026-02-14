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
Phase: 4
Step: Implement WrapMap Logic

## Changes

### 1. `pp-ui-core`

- Added `wrap_line` method to `TextLayout` trait in `src/text.rs`.
- Implemented `wrap_line` in `NoOpLayout` (src/text.rs) and `GpuiTextLayout` (src/text/gpui.rs).
- `wrap_line` returns a `Vec<usize>` containing byte offsets where the line should wrap.

### 2. `pp-editor-core`

- Added `TabPoint` and `WrapPoint` structs to `src/display_map/mod.rs`.
- Implemented `WrapMap` in `src/display_map/wrap_map.rs`:
  - `sync`: Updates wrap points for a set of lines using a `TextLayout`.
  - `to_wrap_point`: Maps `TabPoint` to `WrapPoint`.
  - `from_wrap_point`: Maps `WrapPoint` back to `TabPoint`.
  - `row_count`: Returns total display row count.
- Added unit tests for `WrapMap`.

## Verification Results

- `cargo check --package pp-editor-core` passed.
- `cargo test display_map::wrap_map::tests --package pp-editor-core` passed.

## Next Steps

- Implement `TabMap` logic (Phase 3 also mentioned it, but it was skipped/scaffolded).
- Integrate all layers in `DisplayMap`.

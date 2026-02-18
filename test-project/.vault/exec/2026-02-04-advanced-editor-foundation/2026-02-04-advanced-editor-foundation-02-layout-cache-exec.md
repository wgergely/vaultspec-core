---
tags:
  - "#exec"
  - "#advanced-editor-foundation"
date: 2026-02-04
related:
  - "[[2026-02-04-advanced-editor-foundation-summary]]"
  - "[[2026-02-04-caching-audit]]"
---

# advanced-editor-foundation layout-cache

Date: 2026-02-05
Task: Implement LineLayoutCache in `pp-ui-core`

## Changes

### `crates/pp-ui-core/Cargo.toml`

- Added `parking_lot` (workspace dependency) to support thread-safe double-buffered caching.

### `crates/pp-ui-core/src/text/gpui.rs`

- Implemented `LineLayoutCache` struct with double-buffering (`previous_frame` and `current_frame`).
- Implemented `CacheKey` that uniquely identifies a line layout by its text, font size, runs, and wrap width.
- Integrated `LineLayoutCache` into `GpuiTextLayout`.
- Updated `layout_line` to check the cache before performing expensive shaping operations.
- Added `finish_frame` method to `GpuiTextLayout` to swap buffers and clear the current frame, matching the reference implementation's `TextSystem` behavior.
- Added unit tests to verify the double-buffering and promotion logic.

## Verification

- `cargo check --package pp-ui-core --all-features` passed.
- `cargo test --package pp-ui-core --all-features` passed, including the new `test_line_layout_cache`.
- Cache correctly promotes items from the previous frame to the current frame on a hit.
- Cache correctly clears items that haven't been used for two consecutive frames.

## Next Steps

- Phase 3: Update `EditorView` and `EditorElement` in `pp-editor-main` to use viewport-restricted rendering and leverage the new `LineLayoutCache`.

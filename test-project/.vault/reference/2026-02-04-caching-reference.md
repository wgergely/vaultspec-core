---
tags:
  - "#reference"
  - "#caching-audit"
date: 2026-02-04
related: []
---

# Reference Codebase Audit: LineLayoutCache & Incremental Layout

Feature: LineLayoutCache & Incremental Layout
Description: The reference implementation's strategy for efficient text layout using line-level caching, viewport-restricted shaping, and GPUI-level layout reuse.
Crate(s): gpui, editor
File(s):

- `ref/zed/crates/gpui/src/text_system/line_layout.rs` (LineLayoutCache implementation)
- `ref/zed/crates/gpui/src/text_system.rs` (TextSystem integration)
- `ref/zed/crates/editor/src/element.rs` (Viewport-based layout logic)
- `ref/zed/crates/gpui/src/window.rs` (GPUI-level layout reuse)

## References

### 1. LineLayoutCache Design

`LineLayoutCache` is the core component responsible for caching shaped lines. It uses a double-buffering strategy (`previous_frame` and `current_frame`) to manage the lifecycle of cached layouts.

- **Cache Key (`CacheKey`)**: Includes `text`, `font_size`, `runs` (styling), `wrap_width`, and `force_width`.
- **Double Buffering**: At the end of each frame, `finish_frame` swaps the current frame with the previous one and clears the new current frame. This ensures that only layouts used in the current or previous frame are kept, preventing memory leaks while allowing reuse across frames.
- **Promotion**: When a layout is requested, if it's found in the `previous_frame`, it is moved (promoted) to the `current_frame`.

### 2. Viewport-Restricted Layout

The `EditorElement` avoids laying out the entire document by restricting shaping to:

- **Visible Rows**: It calculates `start_row` and `end_row` based on the current scroll position and the viewport bounds. Only these rows are passed to `layout_lines`.
- **Longest Row**: It explicitly layouts the longest row in the document (tracked by `EditorSnapshot::longest_row()`) to determine the total scrollable width.

### 3. GPUI-Level Reuse (`reuse_prepaint`)

GPUI provides a mechanism to reuse the entire prepaint state of an element if it hasn't changed.

- `Window::prepaint_index()` records the current number of used lines in the `LineLayoutCache`.
- `Window::reuse_prepaint()` allows an element to "claim" a range of line layouts from the previous frame. This bypasses the need for hash map lookups in the cache, as it directly promotes lines based on their insertion order in the previous frame.

### 4. Incremental Updates

- **DisplayMap**: The `DisplayMap` (and its underlying `BlockMap`, `FoldMap`, etc.) handles document changes incrementally.
- **Snapshotting**: The editor works with immutable snapshots. When a change occurs, a new snapshot is created, but most of the underlying data (and thus the resulting `LineLayout` keys) remains the same.
- **Cached Shaping**: Since the shaping happens in the `TextSystem` (called by `EditorElement`), and `TextSystem` uses `LineLayoutCache`, any line that hasn't changed its text or style will hit the cache.

### 5. Summary of Strategies

| Strategy | Mechanism | Benefit |
| --- | --- | --- |
| **Viewport Culling** | Only layout visible lines | O(visible lines) instead of O(total lines) |
| **Double Buffering** | Swap current/previous frame caches | Bounded memory usage with 1-frame persistence |
| **Structural Reuse** | GPUI `reuse_layouts` via index ranges | Zero-lookup reuse of static UI segments |
| **Longest-Line tracking** | Only layout 1 extra line for width | Correct horizontal scrollbars without document-wide layout |

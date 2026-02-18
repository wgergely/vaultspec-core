---
tags:
  - "#reference"
  - "#text-layout-audit"
date: 2026-02-04
related: []
---

# Reference Codebase: Text Layout & Display Map Audit

**Date:** 2026-02-04
**Source:** `ref/zed/crates/editor` and `ref/zed/crates/gpui`

## 1. High-Level Architecture: `DisplayMap`

The reference implementation separates the "buffer" (raw text) from the "display" (visual representation) using a layered `DisplayMap`. This structure handles all non-isomorphic text transformations.

### Location

- `crates/editor/src/display_map.rs`
- `crates/editor/src/display_map/`

### The Layer Stack

The `DisplayMap` is composed of several nested maps, each transforming the coordinate space:

1. **`InlayMap`** (Bottom): Handles virtual text insertions (type hints, inline diagnostics).
    - Transforms `BufferPoint` <-> `InlayPoint`.
2. **`FoldMap`**: Handles code folding (hiding ranges of text).
    - Transforms `InlayPoint` <-> `FoldPoint`.
3. **`TabMap`**: Expands hard tabs ` ` into spaces for visualization.
    - Transforms `FoldPoint` <-> `TabPoint`.
4. **`WrapMap`**: Handles soft wrapping of long lines based on viewport width.
    - Transforms `TabPoint` <-> `WrapPoint`.
5. **`BlockMap`**: Inserts block-level elements (diagnostics, headers) between lines.
    - Transforms `WrapPoint` <-> `BlockPoint` (DisplayPoint).

### Key Abstractions

- **`DisplayPoint`**: The final visual coordinate (row, column) on the screen.
- **`MultiBuffer`**: The underlying text storage (supports multiple cursors/buffers).
- **`Snapshot`s**: Each map provides a snapshot (e.g., `WrapSnapshot`) for thread-safe reading during rendering.

## 2. Low-Level Rendering: `gpui::TextSystem`

The actual text measurement, shaping, and rendering are handled by `gpui`.

### Location

- `crates/gpui/src/text_system.rs`
- `crates/gpui/src/text_system/line_layout.rs`

### Core Components

- **`TextSystem`**: Manages fonts (`FontId`), metrics (`FontMetrics`), and rasterization caches.
  - Delegates to platform-specific backends (CoreText, DirectWrite, etc.).
- **`WindowTextSystem`**: Wraps `TextSystem` with a `LineLayoutCache` for performance.
- **`layout_line` / `shape_line`**: The primary entry points.
  - Input: `text: &str`, `runs: &[TextRun]` (styling), `font_size`.
  - Output: `LineLayout` (platform-agnostic list of positioned glyphs).

### Text Styling (`TextRun`)

The reference implementation supports rich text styling via `TextRun`.

```rust
pub struct TextRun {
    pub len: usize,
    pub font: Font,
    pub color: Hsla,
    pub background_color: Option<Hsla>,
    pub underline: Option<UnderlineStyle>,
    // ...
}
```

## 3. Integration Blueprint for pp-editor-core

To match the reference implementation's capabilities, we need to:

1. **Adopt the Map Hierarchy**: Implement a simplified version of `DisplayMap` (or at least `WrapMap` and `FoldMap`) in `pp-editor-core`. Our current `TextLayout` trait is too low-level to handle this logic itself; it should be driven *by* the maps.
2. **Abstract the Layout Engine**:
    - Keep `TextLayout` trait.
    - Refine it to accept `TextRun`s (for syntax highlighting and formatting).
    - Create `GpuiTextLayout` in `pp-ui-core` (or a bridge crate) that calls `gpui::TextSystem`.
3. **Markdown Blocks**: The `BlockMap` concept is perfect for our Live Preview requirement. We can insert "Preview Blocks" (images, tables) into the `BlockMap`.

## 4. Code Snippets

### `DisplayMap` Creation

```rust
// editor/src/display_map.rs
pub fn new(...) -> Self {
    let (inlay_map, snapshot) = InlayMap::new(buffer_snapshot);
    let (fold_map, snapshot) = FoldMap::new(snapshot);
    let (tab_map, snapshot) = TabMap::new(snapshot, tab_size);
    let (wrap_map, snapshot) = WrapMap::new(snapshot, ...);
    let block_map = BlockMap::new(snapshot, ...);
    // ...
}
```

### `gpui::TextSystem::shape_line`

```rust
// gpui/src/text_system.rs
pub fn shape_line(
    &self,
    text: SharedString,
    font_size: Pixels,
    runs: &[TextRun],
    force_width: Option<Pixels>,
) -> ShapedLine { ... }
```

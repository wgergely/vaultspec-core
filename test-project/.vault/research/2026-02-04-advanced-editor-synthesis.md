---
tags:
  - "#research"
  - "#advanced-editor-synthesis"
date: 2026-02-04
related:
  - "[[2026-02-04-adopt-zed-displaymap]]"
  - "[[2026-02-04-advanced-editor-foundation-plan]]"
---

# Research: Advanced Editor Foundation Synthesis

**Date:** 2026-02-04
**Topic:** Architectural Synthesis of Reference Codebase Audits for Advanced Editor Features
**Status:** Completed

## Goal

Synthesize the findings from the four core editor audits (Folding, Rendering, Caching, Glyph Atlas) into a unified design for the next stage of `pp-editor` development.

## Core Pillars

### 1. High-Performance Folding (`FoldMap`)

The reference implementation uses a piecewise transformation approach.

- **Data Structure:** `SumTree<Transform>` where transforms are either `Isomorphic` (BufferRow -> DisplayRow) or `Folded` (BufferRange -> DisplayRow).
- **CreaseMap:** A higher-level map that tracks user-defined creases (ranges that *can* be folded). `FoldMap` is the active projection of these creases.
- **Integration:** Must be placed in the `DisplayMap` hierarchy: `Buffer -> Inlay -> Fold -> Tab -> Wrap -> Block`.

### 2. Viewport-Restricted Rendering

Rendering must scale independently of document size.

- **Viewport Strategy:** Only compute layouts and draw commands for lines within `scroll_y .. scroll_y + viewport_height`.
- **Longest Line Tracking:** Track the width of the longest line separately to ensure horizontal scrollbars are accurate without laying out the whole document.

### 3. Incremental Layout Caching

Shaping text is expensive.

- **LineLayoutCache:** A double-buffered cache (`prev` and `curr` frames).
- **Keying:** Cache results by `(String, Vec<TextRun>, wrap_width)`.
- **GPUI Integration:** Use the `reuse_prepaint` pattern where the `EditorElement` can efficiently re-use entire layout blocks if the underlying buffer version hasn't changed.

### 4. Advanced Glyph Atlas & Staging

GPU throughput is critical for high-DPI displays.

- **Triple-Atlas:** Separate textures for:
  - `Monochrome` (1-byte, standard text).
  - `Subpixel` (3-4 bytes, high-clarity text).
  - `Polychrome` (4-byte, emojis/images).
- **BufferBelt:** Use a staging buffer pattern for CPU-to-GPU transfers to avoid blocking the render thread.

## Proposed Path

1. **Refactor `DisplayMap`** to include the `FoldMap` layer using the `SumTree` pattern established in `BlockMap`.
2. **Implement `LineLayoutCache`** in `pp-ui-core` to optimize the `GpuiTextLayout`.
3. **Optimize `EditorView`** to be strictly viewport-restricted.
4. **Upgrade `TextRenderer`** to the triple-atlas system.

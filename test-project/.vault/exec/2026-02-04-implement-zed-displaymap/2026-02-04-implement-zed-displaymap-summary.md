---
tags:
  - "#exec"
  - "#implement-zed-displaymap"
date: 2026-02-04
related:
  - "[[2026-02-04-implement-zed-displaymap-plan]]"
  - "[[2026-02-04-implement-zed-displaymap-01-define-types]]"
  - "[[2026-02-04-implement-zed-displaymap-02-update-trait]]"
  - "[[2026-02-04-implement-zed-displaymap-03-create-gpuilayout]]"
  - "[[2026-02-04-implement-zed-displaymap-04-implement-trait]]"
  - "[[2026-02-04-implement-zed-displaymap-05-scaffold-displaymap]]"
  - "[[2026-02-04-implement-zed-displaymap-06-implement-blockmap]]"
  - "[[2026-02-04-implement-zed-displaymap-07-implement-wrapmap]]"
---

# implement-zed-displaymap summary

**Date:** 2026-02-04
**Status:** Completed

## Goal

Implement a robust text layout architecture inspired by the reference implementation's `DisplayMap` to support complex features like soft wrapping, code folding, and "Obsidian-like" Live Preview (blocks), backed by high-performance `gpui` text rendering.

## Key Achievements

### 1. Architectural Refactoring (Phase 1)

- **Moved TextLayout to pp-ui-core:** The `TextLayout` trait and associated types (`TextRun`, `FontId`) were migrated from `pp-editor-core` to `pp-ui-core`.
  - *Rationale:* This resolved a circular dependency where `pp-ui-core` needed to implement a trait defined in `pp-editor-core`.
- **Rich Text Support:** Updated the trait to support `TextRun`s, allowing for syntax highlighting and markdown formatting (bold, italic, color).

### 2. GPUI Implementation (Phase 2)

- **GpuiTextLayout:** Created a concrete implementation of `TextLayout` in `crates/pp-ui-core/src/text/gpui.rs`.
- **Integration:** This adapter wraps `gpui::TextSystem`, enabling the editor to use hardware-accelerated text measurement and layout.
- **Fallback Strategy:** Due to visibility restrictions on some `gpui` methods (`layout_line`), a robust fallback using `TextSystem::advance` was implemented to ensure accurate text measurement and cursor positioning.

### 3. BlockMap for Live Preview (Phase 3)

- **Logic:** Implemented `BlockMap` in `pp-editor-core`. This component allows inserting "virtual" vertical space (blocks) into the editor without modifying the underlying text buffer.
- **Use Case:** This is the engine for "Live Preview", allowing images, tables, or headers to be rendered in-line.
- **Coordinate Mapping:** Implemented robust `to_display_point` and `from_display_point` logic to translate between the buffer and the visual screen, accounting for inserted blocks.

### 4. WrapMap for Soft Wrapping (Phase 4)

- **Logic:** Implemented `WrapMap` to handle soft-wrapping of long lines based on viewport width.
- **Trait Extension:** Added `wrap_line` to the `TextLayout` trait to delegate the complex logic of finding break points to the underlying text system (GPUI).

## Artifacts

- **Plan:** `.docs/plan/2026-02-04-implement-zed-displaymap.md`
- **Code:**
  - `crates/pp-ui-core/src/text.rs` (Trait definition)
  - `crates/pp-ui-core/src/text/gpui.rs` (GPUI implementation)
  - `crates/pp-editor-core/src/display_map/` (DisplayMap hierarchy, BlockMap, WrapMap)

## Next Steps

- Wire `DisplayMap` into the main `Editor` struct.
- Implement the actual rendering of blocks in the UI layer using the coordinates provided by `BlockMap`.

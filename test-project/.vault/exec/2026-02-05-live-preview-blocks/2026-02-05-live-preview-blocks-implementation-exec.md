---
tags:
  - "#exec"
  - "#live-preview-blocks"
date: 2026-02-05
related:
  - "[[2026-02-05-live-preview-blocks-plan]]"
---

# live-preview-blocks implementation

**Date:** 2026-02-05
**Task:** Implement specific "Live Preview" blocks (Image and Table).

## 1. Block Infrastructure Refinement

- Refactored `crates/pp-editor-main/src/blocks.rs` into a module directory `crates/pp-editor-main/src/blocks/`.
- Updated `CustomBlock` to implement `Debug` (required by `EditorModel`) and use proper lifetimes for `BlockContext<'_>`.

## 2. Image Block Implementation

- **File:** `crates/pp-editor-main/src/blocks/image.rs`
- **Functionality:** `ImageBlock::insert`
- **Rendering:** Uses GPUI's `img()` element with `object_fit(Contain)`. Wraps in a fixed-height `div` to match the `DisplayMap` reservation.

## 3. Table Block Implementation

- **File:** `crates/pp-editor-main/src/blocks/table.rs`
- **Functionality:** `TableBlock::insert`
- **Rendering:** Renders a grid of data using nested `flex_col` and `flex_row` `div`s. Applies theme-aware styling (borders, muted header background).

## 4. Verification

- `cargo check -p pp-editor-main` passes cleanly.
- Code integrates with the previously established `EditorModel` and `EditorView` infrastructure.

## Next Steps

- **Dynamic Resizing:** Implement logic to update `BlockProperties` height when the image loads or table content changes (currently uses fixed height passed at insertion).
- **Interactivity:** Add click handlers to blocks (e.g., to select them or open image viewer).

---
tags:
  - "#reference"
  - "#dynamic-blocks-audit"
date: 2026-02-05
related: []
---

# Zed Audit: Dynamic Blocks & Interactive Elements

**Date:** 2026-02-05
**Reference:** `ref/zed/crates/editor/src/`

## 1. Dynamic Block Resizing

Zed handles dynamic block resizing through a feedback loop between the rendering phase (`EditorElement`) and the model phase (`BlockMap`).

### Mechanism

1. **Detection during Paint**: In `element.rs`, when a block is rendered, its actual layout height (computed by GPUI) is compared against the height currently reserved in the `BlockMap`.

    ```rust
    // ref/zed/crates/editor/src/element.rs
    if element_height_in_lines != block.height() {
        resized_blocks.insert(custom_block_id, element_height_in_lines);
    }
    ```

2. **Notification**: These mismatches are collected into a `resized_blocks` map.
3. **Update**: After the rendering pass, the `Editor` calls `self.resize_blocks(heights, cx)`.
4. **DisplayMap Synchronization**: The `BlockMap` updates the height of the specific `BlockId` and rebuilds relevant parts of the `SumTree`. Crucially, it tracks these changes using `Patch` to notify other systems of visual shifts.

### Missing in `pp-editor-main`

- **Height Feedback Loop**: Our `EditorElement` currently accepts a fixed `height` from the model and doesn't measure the actual height of the `AnyElement`.
- **`resize_block` API**: We need a way to update an existing block's height in `pp-editor-core` without a full remove/insert cycle.

## 2. Interactive Markdown Elements

Zed leverages GPUI's unified element model for interactivity within blocks.

### Mechanism

- **Unified Elements**: Markdown "blocks" (like images or tables) are just standard GPUI elements (`AnyElement`).
- **Event Propagation**: Standard GPUI event handlers (`on_click`, `on_mouse_down`, `track_focus`) are used directly on the elements returned by the block renderer.
- **Focus Management**: `prepaint_as_root` returns an optional `FocusHandle`. Zed's `layout_blocks` captures this and notifies the `Editor` to track which block is currently focused.

    ```rust
    // ref/zed/crates/editor/src/element.rs
    let focus_handle = block.element.prepaint_as_root(origin, available_space, window, cx);
    if let Some(focus_handle) = focus_handle {
        editor.set_focused_block(...);
    }
    ```

## 3. Feature Gaps & Recommendations

### Gaps

1. **Actual Height Measurement**: `EditorElement` should measure the height of the `AnyElement` after layout and report it back if it differs from the expected height.
2. **Model-View Sync for Resizing**: Implement a mechanism to propagate reported height changes back to the `EditorModel`.
3. **Focus Integration**: Update `EditorElement` to return the `FocusHandle` from `prepaint_as_root` to the `EditorView`.

### Recommendations for Task 7

- **Extend `BlockMap`**: Add a `resize(id, new_height)` method to `pp-editor-core/src/display_map/block_map.rs`.
- **Implement Measurement in `EditorElement`**: Use the `LayoutId` of the block element to get its resolved size and compare it with the reserved space.
- **Add Resizing API to `EditorModel`**: A method to bridge the UI height reports to the core `BlockMap`.

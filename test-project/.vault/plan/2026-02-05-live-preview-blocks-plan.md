---
tags:
  - "#plan"
  - "#live-preview-blocks"
date: 2026-02-05
related:
  - "[[2026-02-05-editor-demo-architecture]]"
  - "[[2026-02-04-adopt-zed-displaymap]]"
---

# Implementation Plan - Task 6: Live Preview Block Rendering

**Goal:** Implement rendering of custom UI widgets (blocks) interleaved with text in the editor, replacing the current placeholders.

## Architecture

- **`pp-editor-core`**: Remains framework-agnostic. `DisplayMap` tracks block positions/sizes via `BlockId`.
- **`pp-editor-main`**: Handles GPUI integration.
  - `EditorModel` stores the actual block definitions (`CustomBlock`) and renderers.
  - `EditorView` resolves `BlockId`s to `AnyElement`s during the render cycle.
  - `EditorElement` (the custom GPUI element) is responsible for laying out and painting these block elements alongside the text.

## Steps

### 1. Define Block Types (`pp-editor-main`)

Create `crates/pp-editor-main/src/display/blocks.rs`:

- `BlockContext`: Struct exposing relevant context (`Window`, `App`, `Theme`, `Bounds`, etc.) to the renderer.
- `BlockRenderer`: Type alias for `Box<dyn Fn(&mut BlockContext) -> AnyElement + Send + Sync>`.
- `CustomBlock`: Struct holding `BlockId`, `BlockProperties`, and `BlockRenderer`.

### 2. Extend `EditorModel`

- Add `custom_blocks: HashMap<BlockId, CustomBlock>` to `EditorModel`.
- Implement `insert_block(position, height, renderer) -> BlockId`.
  - Inserts into `self.state.display_map`.
  - Stores the renderer in `custom_blocks`.

### 3. Update `EditorView` Rendering Logic

- In `render()`, iterating `render_items`:
  - When `RenderItem::Block(id)` is found:
    - Retrieve `CustomBlock` from `EditorModel`.
    - Invoke `render(&mut ctx)` to produce `AnyElement`.
- Pass a map `HashMap<BlockId, AnyElement>` to `EditorElement::new`.

### 4. Update `EditorElement` (Layout & Paint)

- Add `children: Vec<AnyElement>` (or Map) to `EditorElement`.
- **`request_layout`**:
  - Iterate over block children and call `child.request_layout()`.
- **`paint`**:
  - Iterate `items`.
  - If `Block(id)`:
    - Retrieve the laid-out child element.
    - Calculate its position (already known via `DisplayMap` y-offsets).
    - Call `child.paint()`.

### 5. Verification

- Create a test/example that inserts a "Hello World" block (simple `div().bg(red)`).
- Verify it renders at the correct position and moves with text edits.

## Dependencies

- `gpui`
- `pp-editor-core`

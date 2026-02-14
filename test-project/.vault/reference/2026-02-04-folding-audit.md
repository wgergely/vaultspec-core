---
tags:
  - "#reference"
  - "#folding-audit"
date: 2026-02-04
related: []
---

# Reference Codebase Audit: Code Folding (FoldMap and CreaseMap)

Feature: Code Folding
Description: Architecture for managing folded text ranges, providing both inline transformations and higher-level fold intent management.
Crate(s): `crates/editor`
File(s):

- `crates/editor/src/display_map/fold_map.rs`
- `crates/editor/src/display_map/crease_map.rs`
- `crates/editor/src/display_map.rs`

## References

The reference implementation's folding system is built as a layer in the `DisplayMap` hierarchy, positioned above `InlayMap` and below `TabMap`. It uses a dual-structure approach: `FoldMap` for the mechanical text transformation and `CreaseMap` for managing the user's folding intent.

### 1. FoldMap: The Transformation Layer

`FoldMap` is responsible for transforming the coordinate space of the layer below (`InlayMap`) into a space where folded ranges are collapsed into placeholders.

- **Data Structure**:
  - `folds`: A `SumTree<Fold>` that tracks the active folded ranges using `MultiBuffer` anchors. Anchors ensure folds stay stable as the buffer is edited.
  - `transforms`: A `SumTree<Transform>` that defines the mapping between `InlayPoint` and `FoldPoint`.
- **Transformation Logic**:
  - The `transforms` tree is rebuilt during `FoldMap::sync`.
  - It consists of `Isomorphic` transforms (where input and output are identical) and `Fold` transforms.
  - A `Fold` transform maps a non-empty range in the input to a single-character placeholder ("⋯") in the output.
- **Coordinate Mapping**:
  - `to_fold_point(InlayPoint) -> FoldPoint`
  - `to_inlay_point(FoldPoint) -> InlayPoint`
  - These are implemented via binary search (seek/find) on the `transforms` `SumTree`.

### 2. CreaseMap: The Intent Layer

`CreaseMap` tracks what *can* be folded or what is *explicitly* marked for special display (like a block of code replaced by a summary).

- **Crease Types**:
  - `Crease::Inline`: A standard fold that collapses text into a placeholder.
  - `Crease::Block`: A fold that replaces a range of lines with a custom `gpui` element (Block).
- **Functionality**:
  - Stores `Crease` items in a `SumTree`.
  - Provides metadata for rendering fold indicators (toggles/chevrons) in the gutter.
  - `DisplayMap::fold(Vec<Crease>)` is the entry point that applies these creases, delegating `Inline` ones to `FoldMap` and `Block` ones to `BlockMap`.

### 3. Interaction with InlayMap

`FoldMap` sits directly on top of `InlayMap`.

- It receives `InlaySnapshot` and `InlayEdit`s.
- It must account for inlays when calculating its own transforms, as inlays may exist within or adjacent to folded ranges.

### 4. Placeholder Rendering

Folded ranges are not just "hidden" text; they are replaced by rendered elements.

- **FoldPlaceholder**: Contains a `render` callback: `Arc<dyn Fn(FoldId, Range<Anchor>, &mut App) -> AnyElement>`.
- **Chunk Rendering**: When the editor requests text chunks for rendering, `FoldMap` provides `ChunkRenderer` metadata for folded regions.
- **Dynamic Width**: `FoldMap` supports `update_fold_widths`, allowing placeholders to have dynamic, measured widths based on their rendered content.

### 5. Summary Tree Integration

- **FoldSummary**: Tracks `min_start` and `max_end` of folds in a subtree to allow efficient intersection queries.
- **TransformSummary**: Tracks `input` (MBTextSummary) and `output` (MBTextSummary) to allow O(log N) coordinate translation.

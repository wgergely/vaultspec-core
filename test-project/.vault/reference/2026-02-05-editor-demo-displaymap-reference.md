---
tags:
  - "#reference"
  - "#editor-demo"
date: 2026-02-05
related:
  - "[[2026-02-05-editor-demo-research]]"
  - "[[2026-02-04-displaymap-reference]]"
  - "[[2026-02-04-implement-zed-displaymap-summary]]"
  - "[[2026-02-04-caching-audit]]"
---

# Display Map Pipeline: Cross-Reference Audit

Crate(s): `pp-editor-core` (display_map, sum_tree)
File(s):

- `Y:\code\popup-prompt-worktrees\main\crates\pp-editor-core\src\display_map\mod.rs`
- `Y:\code\popup-prompt-worktrees\main\crates\pp-editor-core\src\display_map\inlay_map.rs`
- `Y:\code\popup-prompt-worktrees\main\crates\pp-editor-core\src\display_map\fold_map.rs`
- `Y:\code\popup-prompt-worktrees\main\crates\pp-editor-core\src\display_map\tab_map.rs`
- `Y:\code\popup-prompt-worktrees\main\crates\pp-editor-core\src\display_map\wrap_map.rs`
- `Y:\code\popup-prompt-worktrees\main\crates\pp-editor-core\src\display_map\block_map.rs`
- `Y:\code\popup-prompt-worktrees\main\crates\pp-editor-core\src\sum_tree\mod.rs`
- `Y:\code\popup-prompt-worktrees\main\crates\pp-editor-core\src\sum_tree\cursor.rs`

Zed Reference:

- `Y:\code\popup-prompt-worktrees\main\ref\zed\crates\editor\src\display_map.rs`
- `Y:\code\popup-prompt-worktrees\main\ref\zed\crates\editor\src\display_map\inlay_map.rs`
- `Y:\code\popup-prompt-worktrees\main\ref\zed\crates\editor\src\display_map\fold_map.rs`
- `Y:\code\popup-prompt-worktrees\main\ref\zed\crates\editor\src\display_map\tab_map.rs`
- `Y:\code\popup-prompt-worktrees\main\ref\zed\crates\editor\src\display_map\wrap_map.rs`
- `Y:\code\popup-prompt-worktrees\main\ref\zed\crates\editor\src\display_map\block_map.rs`
- `Y:\code\popup-prompt-worktrees\main\ref\zed\crates\editor\src\display_map\crease_map.rs`
- `Y:\code\popup-prompt-worktrees\main\ref\zed\crates\editor\src\display_map\dimensions.rs`
- `Y:\code\popup-prompt-worktrees\main\ref\zed\crates\editor\src\display_map\custom_highlights.rs`
- `Y:\code\popup-prompt-worktrees\main\ref\zed\crates\sum_tree\src\sum_tree.rs`
- `Y:\code\popup-prompt-worktrees\main\ref\zed\crates\sum_tree\src\cursor.rs`

---

## Executive Summary

Our display_map pipeline follows Zed's layered architecture (Buffer -> Inlay -> Fold -> Tab -> Wrap -> Block) and has been upgraded to use SumTree-based storage in FoldMap, WrapMap, and BlockMap. However, it remains structurally incomplete compared to Zed's production implementation in several critical dimensions:

1. **No Snapshot Architecture** -- Zed uses immutable snapshots at every layer for thread-safe concurrent access; we have none.
2. **No Edit Propagation Chain** -- Zed propagates `Edit<T>` patches through each layer's `sync()` method; we rebuild from scratch.
3. **InlayMap and TabMap are stubs** -- no implementation at all.
4. **No Chunk/BufferRows iterators** -- Zed provides efficient streaming iterators for rendering; we have none.
5. **SumTree is simplified** -- missing `append`, `slice`, `from_iter`, `update_last`, `FilterCursor`, `Dimensions` tuple type, `SeekTarget` trait, and contextful summaries.

---

## 1. Transform/Summary Pattern

### Zed Pattern (Canonical)

Every layer defines:

| Component | Purpose |
|-----------|---------|
| `Transform` (enum or struct) | Region of text managed by this layer (Isomorphic pass-through vs layer-specific transform) |
| `TransformSummary` | Struct with `input: TextSummary` and `output: TextSummary` |
| `impl Item for Transform` | Returns `TransformSummary` via `summary()` |
| Dimension newtypes | For seeking by input or output coordinate spaces |

**InlayMap** (`ref/zed/.../inlay_map.rs:54-94`):

```rust
enum Transform {
    Isomorphic(MBTextSummary),   // pass-through region
    Inlay(Inlay),                // injected virtual text
}
struct TransformSummary {
    input: MBTextSummary,        // text from buffer (zero for inlays)
    output: MBTextSummary,       // text after inlays inserted
}
```

**FoldMap** (`ref/zed/.../fold_map.rs:330-359`):

```rust
struct Transform {
    summary: TransformSummary,
    placeholder: Option<TransformPlaceholder>,  // None = Isomorphic, Some = Fold
}
struct TransformSummary {
    input: MBTextSummary,
    output: MBTextSummary,
}
```

**WrapMap** (`ref/zed/.../wrap_map.rs:54-64`):

```rust
struct Transform {
    summary: TransformSummary,
    display_text: Option<&'static str>,  // None = Isomorphic, Some = wrap indent/newline
}
struct TransformSummary {
    input: TextSummary,
    output: TextSummary,
}
```

**TabMap**: Unique -- no SumTree. Uses `TabSnapshot` with a `FoldSnapshot` reference and computes tab expansion on-the-fly via column arithmetic. Column expansion is bounded by `max_expansion_column` (256) for performance.

### Our Pattern

| Layer | Transform Type | Summary Type | SumTree? |
|-------|---------------|-------------|----------|
| InlayMap | STUB (empty struct) | None | No |
| FoldMap | `FoldItem::Neutral/Folded` | `FoldSummary { input_rows, output_rows }` | Yes |
| TabMap | STUB (empty struct) | None | No |
| WrapMap | `WrapItem { wrap_points: Vec<u32> }` | `WrapSummary { tab_rows, wrap_rows }` | Yes |
| BlockMap | `BlockItem::Neutral/Block` | `BlockSummary { buffer_rows, display_rows }` | Yes |

### Gap Analysis

**Critical**: Our summaries only track row counts. Zed's summaries carry full `TextSummary` (lines, bytes, UTF-16 offsets, longest_row). This means:

- We cannot do column-level coordinate mapping within a layer.
- We cannot compute text metrics (line lengths, byte offsets) from summaries.
- Chunk iterators cannot emit text content from the transform tree.

**Recommendation**: Adopt `TextSummary { lines: Point, bytes: usize, first_line_chars: u32, last_line_chars: u32 }` as the basis for all transform summaries, enabling both row and column mapping.

---

## 2. Snapshot Architecture

### Zed Pattern

Each layer has a separate `Snapshot` type that captures the immutable state at a point in time:

```
InlaySnapshot { buffer: MultiBufferSnapshot, transforms: SumTree<Transform>, version: usize }
FoldSnapshot  { inlay_snapshot: InlaySnapshot, transforms: SumTree<Transform>, folds: SumTree<Fold>, version: usize }
TabSnapshot   { fold_snapshot: FoldSnapshot, tab_size: NonZeroU32, version: usize }
WrapSnapshot  { tab_snapshot: TabSnapshot, transforms: SumTree<Transform>, interpolated: bool }
BlockSnapshot { wrap_snapshot: WrapSnapshot, transforms: SumTree<Transform>, ... }
DisplaySnapshot { block_snapshot: BlockSnapshot, crease_snapshot: CreaseSnapshot, text_highlights, ... }
```

Key properties:

- **Nesting**: Each snapshot holds the snapshot of the layer below via `Deref`. `DisplaySnapshot.buffer_snapshot()` drills through 5 layers.
- **Arc-based COW**: SumTree uses `Arc<Node<T>>` for O(1) clone, enabling cheap snapshot creation.
- **Versioning**: Each snapshot carries a `version: usize` that increments on any change, enabling efficient staleness checks.

The `DisplayMap::snapshot()` method synchronizes all layers, producing a fresh `DisplaySnapshot` that is then used immutably by the renderer on a separate thread.

### Our Pattern

We have a single mutable `DisplayMap` struct holding all layer instances directly. No snapshots exist. The renderer reads the same mutable state that edits mutate.

### Gap Analysis

**Critical for interactive demo**: Without snapshots, we cannot safely render while processing edits. For the demo this may be acceptable if we render synchronously on the main thread. For production, this must be addressed.

**Recommendation for demo**: Create lightweight `DisplayMapSnapshot` that clones the SumTree roots (O(1) via Arc). Full per-layer snapshots can come later.

---

## 3. Coordinate Systems

### Zed Coordinate Types

| Layer | Point Type | Row Type | Offset Type |
|-------|-----------|----------|-------------|
| Buffer | `MultiBufferPoint(Point)` | `MultiBufferRow(u32)` | `MultiBufferOffset(usize)` |
| Inlay | `InlayPoint(Point)` | -- | `InlayOffset(MultiBufferOffset)` |
| Fold | `FoldPoint(Point)` | -- | `FoldOffset(usize)` |
| Tab | `TabPoint(Point)` | -- | -- |
| Wrap | `WrapPoint(Point)` | `WrapRow(u32)` | -- |
| Block | `BlockPoint(Point)` | `BlockRow(u32)` | -- |
| Display | `DisplayPoint(BlockPoint)` | `DisplayRow(u32)` | -- |

All point types wrap `language::Point { row: u32, column: u32 }`. They implement `sum_tree::Dimension` for their layer's `TransformSummary`.

`dimensions.rs` provides a `impl_for_row_types!` macro and `RowDelta` type for row arithmetic with overflow protection.

### Our Coordinate Types

| Type | Fields | Wraps Point? | Implements Dimension? |
|------|--------|-------------|----------------------|
| `BufferPoint` | `row: u32, column: u32` | No (standalone struct) | No |
| `InlayPoint` | `row: u32, column: u32` | No | No |
| `FoldPoint` | `row: u32, column: u32` | No | No |
| `TabPoint` | `row: u32, column: u32` | No | No |
| `WrapPoint` | `row: u32, column: u32` | No | No |
| `DisplayPoint` | `row: u32, column: u32` | No | No |

### Gap Analysis

- **No Row newtypes**: Zed uses `WrapRow(u32)`, `BlockRow(u32)`, `DisplayRow(u32)` for type-safe row indexing. We use bare `u32`.
- **No Offset types**: Zed uses `InlayOffset`, `FoldOffset` for byte-level precision. We only have row+column.
- **No Dimension implementations**: Our point types cannot be used as SumTree seek targets. The FoldMap and WrapMap use ad-hoc `InputRowDim`/`OutputRowDim` structs instead.
- **No `Point` wrapper**: Zed's points wrap a common `language::Point` which provides arithmetic operations. Ours are standalone structs with duplicate Display impls.

**Recommendation**: Create a shared `Point { row: u32, column: u32 }` base type, then newtype-wrap it for each coordinate space. Implement `Dimension<TransformSummary>` on each.

---

## 4. SumTree Implementation Comparison

### Zed's SumTree (`ref/zed/crates/sum_tree/src/sum_tree.rs`)

| Feature | Zed | Ours |
|---------|-----|------|
| Node structure | `Arc<Node<T>>` B+ tree | Same |
| TREE_BASE | 6 (2 in test) | 6 |
| `push()` | Yes | Yes |
| `append(tree)` | Yes -- O(log N) tree merge | **Missing** |
| `slice(target, bias)` (via Cursor) | Yes -- O(log N) split | **Missing** |
| `from_iter()` | Yes | **Missing** |
| `from_item()` | Yes | **Missing** |
| `update_last()` | Yes -- mutate last item in-place | **Missing** |
| `items()` | Yes -- collect all items | **Missing** |
| `iter()` | Yes -- iterate items | **Missing** |
| Summary trait | `Context<'a>: Copy` lifetime-parameterized | `Context` as associated type (no lifetime) |
| `ContextLessSummary` | Blanket impl for `Summary` where `Context = ()` | N/A (our Summary always has `Context`) |
| Dimension trait | `Dimension<'a, S>` with `zero(cx)` | `Dimension<S>: Clone + Default + Ord` |
| `Dimensions<D1, D2, D3>` tuple | Yes -- seek by one dim, read others | **Missing** |
| `SeekTarget` trait | Yes -- custom seek comparison | **Missing** |
| `FilterCursor` | Yes -- skip items that don't match predicate | **Missing** |
| `TreeMap<K, V>` | Yes -- ordered map on top of SumTree | **Missing** |
| `TreeSet<K>` | Yes | **Missing** |
| Rayon parallel construction | Yes | **Missing** |
| `Bias` default | `Left` | `Right` |

### Critical Missing SumTree Operations

1. **`cursor.slice(target, bias)`**: This is the most important missing operation. Zed's edit propagation (`sync()` in every layer) works by:

   ```
   new_tree.append(cursor.slice(&edit.old.start, Bias::Left));
   // process edit region
   cursor.seek(&edit.old.end, Bias::Right);
   // continue
   new_tree.append(cursor.suffix());
   ```

   Without `slice()` and `append()`, incremental updates are impossible -- we must rebuild the entire tree.

2. **`Dimensions<D1, D2, D3>`**: Enables seeking by one dimension while simultaneously tracking position in other dimensions. Used extensively: `Cursor<Transform, Dimensions<FoldPoint, InlayPoint>>`.

3. **`update_last()`**: Used in fold_map sync to merge adjacent isomorphic transforms without allocating a new node.

### Cursor Comparison

| Feature | Zed | Ours |
|---------|-----|------|
| `seek()` | By `SeekTarget` trait | By `D: Ord` |
| `next()` | Yes | Yes |
| `prev()` | Yes | **Missing** |
| `slice()` | Returns new SumTree of everything before cursor | **Missing** |
| `suffix()` | Returns new SumTree of everything after cursor | **Missing** |
| `start()` / `end()` | Returns `Dimensions` tuple | `start()` only, returns single `D` |
| `start_as::<D2>()` | N/A (uses Dimensions tuple) | Yes (ad-hoc) |
| `item_summary()` | Yes | **Missing** |
| Multi-dimensional | Via `Dimensions<D1, D2, D3>` | Via separate `start_as::<D2>()` calls |

**Recommendation**: Implement `slice()`, `append()`, and `suffix()` on SumTree/Cursor as priority #1. These unlock incremental edit propagation.

---

## 5. Edit Propagation

### Zed's Incremental Edit Pipeline

When the buffer changes, edits propagate through each layer:

```
buffer_edits: Vec<Edit<MultiBufferOffset>>
  |
  v  InlayMap::sync(buffer_snapshot, buffer_edits) -> (InlaySnapshot, Vec<InlayEdit>)
  |
  v  FoldMap::read(inlay_snapshot, inlay_edits) -> (FoldSnapshot, Vec<FoldEdit>)
  |
  v  TabMap::sync(fold_snapshot, fold_edits, tab_size) -> (TabSnapshot, Vec<TabEdit>)
  |
  v  WrapMap::sync(tab_snapshot, tab_edits) -> (WrapSnapshot, WrapPatch)
  |
  v  BlockMap::read(wrap_snapshot, wrap_patch, companion) -> BlockMapReader { snapshot }
```

Each layer's `sync()`:

1. Takes the new lower-layer snapshot and a list of edits from the lower layer.
2. Uses `cursor.slice()` to efficiently copy unchanged prefix.
3. Processes the edit region (re-mapping folds, recomputing wraps, etc.).
4. Uses `cursor.suffix()` to copy unchanged suffix.
5. Returns a new snapshot and a list of edits in its own coordinate space.

Edit types change at each layer boundary:

- `Edit<MultiBufferOffset>` -> `Edit<InlayOffset>` -> `Edit<FoldOffset>` -> `Edit<TabPoint>` -> `Edit<WrapRow>`

### Our Current Approach

`DisplayMap::sync()` only calls `self.wrap_map.sync(lines, layout, wrap_width)` which **rebuilds the entire WrapMap from scratch**. No edits flow through any layer. The FoldMap and BlockMap are not synced at all during text changes.

### Gap Analysis

**Critical**: Without incremental edit propagation, every keystroke rebuilds the entire WrapMap tree. For a 10,000-line file, this is O(N) per keystroke instead of O(log N + E) where E is the edit size.

**Recommendation for demo**: Acceptable for small demo files (<1000 lines). For production, implement the full edit pipeline after SumTree gains `slice`/`append`/`suffix`.

---

## 6. WrapMap Async Wrapping

### Zed's Approach (`ref/zed/.../wrap_map.rs:104-255`)

- `WrapMap` is a **GPUI Entity** (`Entity<WrapMap>`), not a plain struct.
- `rewrap()` spawns a `background_task` via `cx.background_spawn()`.
- Uses `block_with_timeout(5ms)` to attempt synchronous completion first.
- If the wrap takes longer than 5ms, it enters an **interpolated** state:
  - The old snapshot is used with interpolated edits.
  - When the background task completes, the real edits are composed with the interpolated edits via `compose()`.
- `pending_edits: VecDeque<(TabSnapshot, Vec<TabEdit>)>` queues edits that arrive while a background wrap is in progress.
- `flush_edits()` processes pending edits either synchronously or via another background task.
- Uses GPUI's `LineWrapper` (backed by the GPU text system) for actual wrap computation.

### Our Approach

- `WrapMap` is a plain `struct` (not a GPUI entity).
- `sync()` is fully synchronous and rebuilds the entire tree.
- Uses a `TextLayout` trait with `wrap_line()` that returns byte offsets.
- No background processing, no interpolation, no pending edit queue.

### Gap Analysis

For the demo, synchronous wrapping is fine. For production with large files, the async pattern is essential. Key requirements:

1. WrapMap must become a GPUI `Entity` to receive notifications.
2. Need `Patch<WrapRow>` type for composable edit patches.
3. Need `interpolated` flag and `pending_edits` queue.
4. Integration with GPUI's text system for accurate line wrapping.

---

## 7. BlockMap Placement Strategies

### Zed's BlockPlacement (`ref/zed/.../block_map.rs:121-180`)

```rust
pub enum BlockPlacement<T> {
    Above(T),          // Place block above position
    Below(T),          // Place block below position
    Near(T),           // Place block next to position (inline)
    Replace(RangeInclusive<T>),  // Replace a range of text with the block
}
```

- Generic over `T` (typically `Anchor` for storage, `WrapRow` for rendering).
- `Replace` blocks can hide multi-line ranges and replace them with custom rendered content.
- Blocks carry `RenderBlock` closures, `height`, `BlockStyle`, and `priority`.
- `BlockMapWriter` provides `insert()` and `remove()` with full edit propagation.
- `BlockSnapshot` provides iterators: `BlockChunks`, `BlockRows` for efficient rendering.
- Supports `StickyHeaderExcerpt` and `CompanionView` for split editor layouts.
- `EditorMargins` controls left/right margin blocks.

### Our BlockPlacement

```rust
pub enum BlockPlacement {
    Above,
    Below,
}
```

- Not generic -- position stored separately in `BlockItem::Block { position: u32, ... }`.
- No `Replace` variant (critical for markdown live preview).
- No `Near` variant.
- No render closures -- blocks are abstract row offsets only.
- No `BlockMapWriter` pattern -- direct mutable access with full tree rebuild on insert/remove.

### Gap Analysis

**Critical for markdown live preview**: `Replace` blocks are needed to hide markdown syntax and replace it with rendered content (e.g., replacing `**bold**` with rendered bold text, or replacing a code fence with a rendered code block). Without `Replace`, we cannot do live preview.

**Recommendation**: Add `BlockPlacement::Replace(RangeInclusive<T>)` as minimum. Add `RenderBlock` closures for GPUI integration.

---

## 8. CreaseMap

### Zed's CreaseMap (`ref/zed/.../crease_map.rs`)

CreaseMap provides **explicitly foldable ranges** that supersede indentation-based fold detection. It is a companion to FoldMap, not a layer in the transform pipeline.

Key types:

```rust
pub enum Crease<T> {
    Inline {
        range: Range<T>,
        placeholder: FoldPlaceholder,
        render_toggle: Option<RenderToggleFn>,
        render_trailer: Option<RenderTrailerFn>,
        metadata: Option<CreaseMetadata>,
    },
    Block {
        range: Range<T>,
        block_height: u32,
        block_style: BlockStyle,
        render_block: RenderBlock,
        block_priority: usize,
        render_toggle: Option<RenderToggleFn>,
    },
}
```

- `Crease::Inline` -- traditional fold with a placeholder (e.g., `...`).
- `Crease::Block` -- folding that replaces text with a block element.
- `CreaseSnapshot` stores creases in a `SumTree<CreaseItem>` keyed by buffer anchors.
- `query_row()` finds the crease at a given row.
- `creases_in_range()` iterates creases in a row range.
- Used in `DisplayMap::fold()` to create both inline folds and block replacements simultaneously.

### Our Implementation

We have no CreaseMap. Our FoldMap only tracks row ranges, not anchor-based ranges with placeholders.

### Assessment

CreaseMap is **valuable but not critical for demo**. It becomes important when:

- Supporting language-server provided fold ranges.
- Implementing markdown section folding.
- Providing fold toggle UI in the gutter.

**Recommendation**: Defer to post-demo. Implement when adding fold UI.

---

## 9. Additional Zed Components We Lack

### `custom_highlights.rs`

- `CustomHighlightsChunks` wraps `MultiBufferChunks` with overlay highlights.
- Used for text selections, search highlights, diagnostic underlines.
- Provides `HighlightEndpoint` sorted by offset for efficient highlight boundary tracking.
- **Needed for**: selection rendering, search-and-replace highlighting.

### `invisibles.rs`

- `is_invisible()` and `replacement()` functions for rendering whitespace characters.
- **Needed for**: "show whitespace" feature.

### `dimensions.rs`

- `RowDelta(u32)` type for row-level arithmetic.
- `impl_for_row_types!` macro generates `Add`, `Sub`, `AddAssign`, `SubAssign`, `saturating_sub` for row newtypes.
- **Needed for**: type-safe row arithmetic across layers.

---

## 10. Summary of Gaps (Priority Order)

### P0: Required for Interactive Demo

| Gap | Impact | Effort |
|-----|--------|--------|
| InlayMap implementation (at least pass-through) | Broken pipeline if inlays needed | Low (pass-through only) |
| TabMap implementation (at least pass-through) | Tab characters render wrong | Low (pass-through only) |
| `DisplayMap::sync()` calling all layers | Only WrapMap syncs currently | Medium |
| Basic `DisplayMapSnapshot` (clone SumTree roots) | Thread-safety for rendering | Medium |

### P1: Required for Live Preview

| Gap | Impact | Effort |
|-----|--------|--------|
| `BlockPlacement::Replace` | Cannot hide markdown and show rendered content | Medium |
| `RenderBlock` closures on blocks | Cannot render custom block content | Medium |
| Column-level coordinate mapping (TextSummary) | Cannot map cursor within wrapped/folded lines | High |
| SumTree `slice`/`append`/`suffix` | Cannot do incremental updates | High |

### P2: Required for Production Quality

| Gap | Impact | Effort |
|-----|--------|--------|
| Full edit propagation chain | O(N) per keystroke for large files | High |
| WrapMap async background wrapping | UI freezes on large files | High |
| Chunk iterators at every layer | Inefficient rendering | High |
| CreaseMap | No fold UI | Medium |
| CustomHighlights | No selection/search highlighting | Medium |
| Anchor-based positions (instead of row indices) | Positions invalidated by edits | High |

---

## 11. Architectural Alignment Score

| Aspect | Score | Notes |
|--------|-------|-------|
| Layer ordering | 5/5 | Identical: Inlay -> Fold -> Tab -> Wrap -> Block |
| SumTree foundation | 3/5 | Present but missing critical operations |
| Coordinate types | 2/5 | Row-only, no Point wrapping, no Dimension impls |
| Snapshot architecture | 0/5 | Non-existent |
| Edit propagation | 0/5 | Non-existent |
| InlayMap | 0/5 | Stub only |
| FoldMap | 3/5 | SumTree-based, row-level mapping works, no column or edit sync |
| TabMap | 0/5 | Stub only |
| WrapMap | 3/5 | SumTree-based, synchronous-only, full rebuild |
| BlockMap | 3/5 | SumTree-based, missing Replace/Near, no render closures |
| Chunk iterators | 0/5 | Non-existent |
| Highlights | 0/5 | Non-existent |

**Overall: 19/60 (32%)** -- The foundation is correct but the implementation is skeletal.

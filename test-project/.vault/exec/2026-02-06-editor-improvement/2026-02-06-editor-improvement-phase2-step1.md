---
tags:
  - "#step-record"
  - "#phase2"
  - "#incremental-layout"
date: 2026-02-06
phase: 2
step: 1
status: in_progress
related:
  - "[[2026-02-06-editor-improvement-plan]]"
  - "[[2026-02-06-incremental-layout-engine-design-adr]]"
  - "[[2026-02-06-incremental-layout-engine-research]]"
---

# Step 1: Design DisplayMap Architecture and Patch System

## Objective

Create detailed design for the incremental layout algorithm and localized `DisplayMapPatch` objects based on Zed's architecture.

## Current State Analysis

### Existing Infrastructure (Already Implemented)

The codebase already has significant infrastructure in place:

1. **DisplayMap** (`crates/pp-editor-core/src/display_map/mod.rs`):
   - Full layered structure: InlayMap → FoldMap → TabMap → WrapMap → BlockMap
   - Coordinate types defined: `BufferPoint`, `InlayPoint`, `FoldPoint`, `TabPoint`, `WrapPoint`, `DisplayPoint`
   - `sync()` method exists but performs **full recalculation**
   - `to_display_point()` and `from_display_point()` transformations work correctly

2. **SumTree** (`crates/pp-editor-core/src/sum_tree/mod.rs`):
   - Core B+ tree implementation complete
   - Summary and Dimension traits defined
   - Cursor for efficient traversal
   - `split_off()` method partially implemented (marked `unimplemented!()`)
   - `push()` operation fully functional

3. **BlockMap** (`crates/pp-editor-core/src/display_map/block_map.rs`):
   - Uses `SumTree<BlockItem>` internally
   - Supports Above, Below, and Replace placements
   - Has `BlockSummary` with `buffer_rows` and `display_rows`
   - `insert()` method rebuilds entire tree (inefficient)

4. **Patch System** (`crates/pp-editor-core/src/sum_tree/patch.rs`):
   - Basic `TextEdit<T, D>` structure exists
   - Supports insert, delete, replace operations
   - **NOT INTEGRATED** - no `apply_patch()` method on SumTree

### Current Performance Bottleneck

In `EditorState::sync_layout_with_tab_size()` (line ~630 in `state.rs`):

```rust
pub fn sync_layout_with_tab_size(
    &mut self,
    layout: &dyn crate::layout::TextLayout,
    wrap_width: f32,
    tab_size: u32,
) {
    let lines: Vec<String> =
        (0..self.buffer.len_lines()).map(|i| self.buffer.line(i).to_string()).collect();
    self.display_map.sync(&lines, layout, wrap_width, tab_size);
}
```

**Problem**: This rebuilds **all lines** on every call, then calls `DisplayMap::sync()` which:

1. Fully resets `InlayMap`
2. Preserves `FoldMap` state but doesn't incrementally update
3. Fully resets `TabMap`
4. Fully rebuilds `WrapMap` for ALL lines
5. Doesn't update `BlockMap` at all

## Design: Incremental Layout with DisplayMapPatch

### Core Concept

Instead of full recalculation, we introduce **DisplayMapPatch** - a localized change descriptor that represents:

- Which buffer range changed
- What type of change occurred (insert/delete/replace)
- Which display layers are affected

### Architecture

```
Buffer Edit
    ↓
Generate BufferPatch (from buffer version tracking)
    ↓
Transform through DisplayMap layers:
    InlayMap → generates InlayPatch
    FoldMap → generates FoldPatch
    TabMap → generates TabPatch
    WrapMap → generates WrapPatch
    BlockMap → generates BlockPatch
    ↓
Apply patches incrementally using SumTree operations
    ↓
Updated DisplayMap (only affected regions)
```

### Patch Data Structures

#### 1. BufferPatch

```rust
pub struct BufferPatch {
    /// Range of buffer rows affected
    pub start_row: u32,
    pub end_row: u32,
    /// Type of change
    pub kind: BufferPatchKind,
}

pub enum BufferPatchKind {
    /// Lines inserted at start_row
    LinesInserted { count: u32 },
    /// Lines deleted from start_row..end_row
    LinesDeleted { count: u32 },
    /// Lines modified in-place (text changed but line count same)
    LinesModified,
    /// Mixed: complex edit affecting multiple lines
    Mixed,
}
```

#### 2. DisplayMapPatch

```rust
pub struct DisplayMapPatch {
    /// Patches for each layer (applied in order)
    pub inlay_patch: Option<InlayPatch>,
    pub fold_patch: Option<FoldPatch>,
    pub tab_patch: Option<TabPatch>,
    pub wrap_patch: Option<WrapPatch>,
    pub block_patch: Option<BlockPatch>,

    /// Original buffer change that triggered this patch
    pub source: BufferPatch,
}
```

#### 3. Layer-Specific Patches

Each layer defines its own patch type:

```rust
pub struct WrapPatch {
    /// First affected row in wrap-space
    pub start_row: u32,
    /// Last affected row in wrap-space (exclusive)
    pub end_row: u32,
    /// New wrapped lines for this range
    pub new_lines: Vec<WrappedLine>,
}

pub struct BlockPatch {
    /// Blocks to insert (sorted by position)
    pub insertions: Vec<(BufferPoint, Block)>,
    /// Block IDs to remove
    pub removals: Vec<BlockId>,
}
```

### SumTree Incremental Update Strategy

The key to efficiency is using `SumTree` operations to update only affected regions:

1. **For Insertions**:
   - Use `Cursor` to seek to insertion point
   - Split tree at that dimension
   - Insert new items
   - Rejoin trees

2. **For Deletions**:
   - Use `Cursor` to seek to deletion range
   - Split tree at start and end
   - Discard middle section
   - Rejoin remaining trees

3. **For Modifications**:
   - Split at range boundaries
   - Replace middle section with updated items
   - Rejoin trees

### Implementation Plan

#### Phase 2.1: SumTree Edit Operations

Implement missing operations on `SumTree`:

- `insert_at<D>(&mut self, dim: D, items: Vec<T>)` - insert items at dimension
- `remove_range<D>(&mut self, start: D, end: D)` - remove items in range
- `replace_range<D>(&mut self, start: D, end: D, items: Vec<T>)` - replace range
- Complete `split_off()` implementation (currently unimplemented)
- Add `append(&mut self, other: SumTree<T>)` for rejoining

#### Phase 2.2: BufferPatch Generation

Add version tracking to `Buffer`:

- Track `last_synced_version: u64` in `EditorState`
- On `sync_layout()`, compare `buffer.version()` with `last_synced_version`
- Generate `BufferPatch` from operation history or diff

#### Phase 2.3: DisplayMap Incremental Sync

Refactor `DisplayMap::sync()`:

```rust
impl DisplayMap {
    pub fn sync_incremental(
        &mut self,
        buffer_patch: BufferPatch,
        lines: &[String],
        layout: &dyn TextLayout,
        wrap_width: f32,
        tab_size: u32,
    ) -> DisplayMapPatch {
        // Transform patch through each layer
        let inlay_patch = self.inlay_map.apply_buffer_patch(&buffer_patch);
        let fold_patch = self.fold_map.apply_patch(&inlay_patch);
        let tab_patch = self.tab_map.apply_patch(&fold_patch, tab_size);
        let wrap_patch = self.wrap_map.apply_patch(&tab_patch, lines, layout, wrap_width);
        let block_patch = self.block_map.apply_patch(&wrap_patch);

        DisplayMapPatch {
            inlay_patch,
            fold_patch,
            tab_patch,
            wrap_patch,
            block_patch,
            source: buffer_patch,
        }
    }
}
```

#### Phase 2.4: WrapMap Incremental Updates

This is the most complex layer since it interacts with text layout:

```rust
impl WrapMap {
    pub fn apply_patch(
        &mut self,
        tab_patch: &TabPatch,
        lines: &[String],
        layout: &dyn TextLayout,
        wrap_width: f32,
    ) -> WrapPatch {
        // 1. Determine affected line range
        let start_line = tab_patch.start_row;
        let end_line = tab_patch.end_row;

        // 2. Extract and re-layout only affected lines
        let new_wrapped_lines: Vec<WrappedLine> =
            lines[start_line..end_line]
                .iter()
                .map(|line| self.wrap_line(line, layout, wrap_width))
                .collect();

        // 3. Update SumTree using replace_range
        self.tree.replace_range(
            RowDim(start_line),
            RowDim(end_line),
            new_wrapped_lines,
        );

        WrapPatch {
            start_row: start_line,
            end_row: end_line,
            new_lines: new_wrapped_lines,
        }
    }
}
```

### Fallback Strategy

For maximum safety during migration:

1. Implement incremental path alongside existing full-sync
2. Add `incremental: bool` feature flag
3. Compare results in debug mode
4. Gradually enable incremental mode per layer

## Expected Outcomes

1. **SumTree Operations**: Complete edit API for efficient range-based updates
2. **Patch System**: Fully defined data structures for representing localized changes
3. **Incremental Sync**: `DisplayMap` can apply patches instead of full recalculation
4. **Version Tracking**: `EditorState` tracks when layout was last synced

## Next Steps

- Step 2: Implement missing SumTree operations
- Step 3: Integrate patch system into each DisplayMap layer
- Step 4: Refactor `sync_layout()` to use incremental updates
- Step 5: Benchmark and verify correctness

## Notes

The existing infrastructure is surprisingly complete! The main gap is:

1. Missing `SumTree` edit operations (split/insert/remove/replace/append)
2. No patch generation or application logic
3. `sync_layout()` doesn't track what changed

This is a **refactor** more than a **new implementation** - the architecture is already correct per ADR-0003.

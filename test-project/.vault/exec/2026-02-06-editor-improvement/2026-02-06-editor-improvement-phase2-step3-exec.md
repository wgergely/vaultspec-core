---
tags:
  - "#exec"
  - "#step-record"
  - "#phase2"
  - "#incremental-layout"
date: 2026-02-06
related:
  - "[[2026-02-06-editor-improvement-plan]]"
  - "[[2026-02-06-editor-improvement-phase2-step1]]"
  - "[[2026-02-06-editor-improvement-phase2-step2]]"
---
# Step 3: Implement DisplayMap Patch Types and Application Logic

## Objective

Define patch data structures for each DisplayMap layer and implement `apply_patch()` methods for incremental updates.

## Patch Type Definitions

### 1. BufferPatch (Source of All Patches)

```rust
// In display_map/mod.rs or new display_map/patch.rs

/// Represents a change to the buffer that requires layout updates
#[derive(Debug, Clone)]
pub struct BufferPatch {
    /// First affected buffer row
    pub start_row: u32,
    /// Last affected buffer row (exclusive)
    pub end_row: u32,
    /// Nature of the change
    pub kind: BufferPatchKind,
}

#[derive(Debug, Clone)]
pub enum BufferPatchKind {
    /// Lines inserted at start_row
    LinesInserted { count: u32 },
    /// Lines deleted (end_row - start_row lines removed)
    LinesDeleted,
    /// Lines modified in-place (same line count, text changed)
    LinesModified,
}
```

### 2. Layer-Specific Patches

```rust
/// Patch for WrapMap - updated wrapped lines
#[derive(Debug, Clone)]
pub struct WrapPatch {
    pub start_row: u32,
    pub end_row: u32,
}

/// Patch for BlockMap - block insertions/removals
#[derive(Debug, Clone)]
pub struct BlockPatch {
    pub insertions: Vec<(BufferPoint, BlockId, u32, BlockPlacement)>,
    pub removals: Vec<BlockId>,
}

/// Patch for FoldMap - fold region updates
#[derive(Debug, Clone)]
pub struct FoldPatch {
    pub affected_range: (u32, u32), // (start_row, end_row)
}
```

## Implementation Strategy

### Phase 3.1: Add Patch Types to display_map Module

Create `crates/pp-editor-core/src/display_map/patch.rs`:

```rust
use super::{BufferPoint, block_map::{BlockId, BlockPlacement}};

/// Complete patch for all DisplayMap layers
#[derive(Debug, Clone, Default)]
pub struct DisplayMapPatch {
    /// Original buffer change
    pub source: BufferPatch,
    /// Affected layers (None = no change in that layer)
    pub wrap_patch: Option<WrapPatch>,
    pub block_patch: Option<BlockPatch>,
    pub fold_patch: Option<FoldPatch>,
}
```

### Phase 3.2: Implement WrapMap::apply_patch()

This is the most critical method. Current `WrapMap::sync()` rebuilds all lines:

```rust
impl WrapMap {
    pub fn apply_patch(
        &mut self,
        buffer_patch: &BufferPatch,
        lines: &[String],
        layout: &dyn TextLayout,
        wrap_width: f32,
    ) -> WrapPatch {
        match buffer_patch.kind {
            BufferPatchKind::LinesModified => {
                // Re-wrap only affected lines
                let start = buffer_patch.start_row as usize;
                let end = buffer_patch.end_row as usize;

                let new_wrapped_lines: Vec<WrappedLine> = lines[start..end]
                    .iter()
                    .enumerate()
                    .map(|(i, line)| {
                        let row = (start + i) as u32;
                        self.wrap_line(line, layout, wrap_width, row)
                    })
                    .collect();

                // Use SumTree::replace_range to update only affected rows
                self.tree.replace_range(
                    &RowDim(buffer_patch.start_row),
                    &RowDim(buffer_patch.end_row),
                    new_wrapped_lines,
                    &(),
                );
            }
            BufferPatchKind::LinesInserted { count } => {
                // Wrap new lines and insert
                let start = buffer_patch.start_row as usize;
                let new_lines = &lines[start..start + count as usize];

                let wrapped: Vec<WrappedLine> = new_lines
                    .iter()
                    .enumerate()
                    .map(|(i, line)| {
                        let row = (start + i) as u32;
                        self.wrap_line(line, layout, wrap_width, row)
                    })
                    .collect();

                self.tree.insert_at(
                    &RowDim(buffer_patch.start_row),
                    wrapped,
                    &(),
                );
            }
            BufferPatchKind::LinesDeleted => {
                // Remove wrapped lines for deleted buffer lines
                self.tree.remove_range(
                    &RowDim(buffer_patch.start_row),
                    &RowDim(buffer_patch.end_row),
                    &(),
                );
            }
        }

        WrapPatch {
            start_row: buffer_patch.start_row,
            end_row: buffer_patch.end_row,
        }
    }
}
```

### Phase 3.3: Implement BlockMap::apply_patch()

Current `BlockMap::insert()` rebuilds the entire tree. We need incremental operations:

```rust
impl BlockMap {
    /// Apply a block patch incrementally
    pub fn apply_patch(&mut self, patch: &BlockPatch) {
        // Remove blocks
        for block_id in &patch.removals {
            self.remove_block(*block_id);
        }

        // Insert blocks (already have insert method, but it rebuilds)
        for (position, _id, height, placement) in &patch.insertions {
            self.insert(*position, *height, *placement);
        }
    }

    /// Remove a block without rebuilding entire tree
    fn remove_block(&mut self, id: BlockId) {
        // Find and remove the block item from the SumTree
        // This requires either:
        // 1. Tracking block positions separately
        // 2. Scanning tree to find block
        // 3. Using a HashMap<BlockId, Position> index

        // For now, rebuild is acceptable (complex optimization)
        let mut blocks = self.all_blocks();
        blocks.retain(|b| b.id != id);
        self.rebuild_from_blocks(blocks);
    }
}
```

### Phase 3.4: Add Version Tracking to Buffer

```rust
// In buffer.rs

#[derive(Clone, Debug)]
pub struct Buffer {
    text: Rope,
    version: u64,  // ← ADD THIS
    line_ending: LineEnding,
}

impl Buffer {
    pub fn insert(&mut self, pos: usize, text: &str) {
        self.text.insert(pos, text);
        self.version += 1;  // ← INCREMENT ON EVERY EDIT
    }

    pub fn delete(&mut self, range: Range<usize>) {
        self.text.remove(range);
        self.version += 1;
    }

    pub fn version(&self) -> u64 {
        self.version
    }
}
```

### Phase 3.5: Add Last Synced Version to EditorState

```rust
// In state.rs

pub struct EditorState {
    buffer: Buffer,
    cursor: Cursor,
    history: History,
    dirty: bool,
    folds: Vec<FoldRegion>,
    display_map: DisplayMap,
    last_synced_version: u64,  // ← ADD THIS
}

impl EditorState {
    pub fn sync_layout_incremental(
        &mut self,
        layout: &dyn TextLayout,
        wrap_width: f32,
        tab_size: u32,
    ) {
        let current_version = self.buffer.version();

        if current_version == self.last_synced_version {
            // No changes, skip sync
            return;
        }

        // Generate BufferPatch from version diff
        let patch = self.generate_buffer_patch(self.last_synced_version, current_version);

        // Apply patch through DisplayMap layers
        let lines: Vec<String> = (0..self.buffer.len_lines())
            .map(|i| self.buffer.line(i).to_string())
            .collect();

        self.display_map.sync_incremental(patch, &lines, layout, wrap_width, tab_size);

        self.last_synced_version = current_version;
    }

    fn generate_buffer_patch(&self, _from_version: u64, _to_version: u64) -> BufferPatch {
        // SIMPLIFIED: For now, mark entire buffer as modified
        // TODO: Track actual changes via operation history or rope diffs
        BufferPatch {
            start_row: 0,
            end_row: self.buffer.len_lines() as u32,
            kind: BufferPatchKind::LinesModified,
        }
    }
}
```

## Current Blockers & Decisions

### Blocker 1: WrapMap Doesn't Use SumTree Yet

**Current Implementation**: `WrapMap` stores `Vec<WrappedLine>` directly, not a `SumTree`.

**Solution**: Refactor `WrapMap` to use `SumTree<WrappedLine>` internally.

```rust
// Current (display_map/wrap_map.rs):
pub struct WrapMap {
    lines: Vec<WrappedLine>,  // ← PROBLEM
}

// Target:
pub struct WrapMap {
    tree: SumTree<WrappedLine>,  // ← SOLUTION
}
```

### Blocker 2: Patch Generation from Buffer Edits

**Options**:

1. **History-Based**: Track operations in `History`, reconstruct changes
2. **Rope Diff**: Compare rope before/after (expensive)
3. **Incremental Tracking**: Store `last_synced_snapshot: Rope`, diff on sync
4. **Operation Hooks**: Capture edits as they happen

**Recommended**: Option 3 (Incremental Tracking) - simple, correct, acceptable performance.

### Blocker 3: FoldMap and TabMap Don't Need Patches

**Observation**:

- `FoldMap` is user-driven (fold/unfold commands), not buffer-driven
- `TabMap` is deterministic from text content

**Decision**: Skip patch logic for these layers initially. They can sync fully since they're lightweight.

## Implementation Plan

### Immediate (This Step)

1. ✅ Add version tracking to `Buffer`
2. ✅ Add `last_synced_version` to `EditorState`
3. ✅ Define `BufferPatch`, `WrapPatch`, `BlockPatch` types
4. ⏳ Refactor `WrapMap` to use `SumTree` internally

### Next Step (Step 4)

1. Implement `WrapMap::apply_patch()` using new SumTree operations
2. Implement `BlockMap::apply_patch()` (incremental inserts/removes)
3. Add `DisplayMap::sync_incremental()` method
4. Add tests for each patch application

### Step 5 (Integration)

1. Replace `sync_layout()` with `sync_layout_incremental()`
2. Add fallback to full sync if patch generation fails
3. Feature flag: `incremental_layout` (default off initially)

## Testing Strategy

```rust
#[test]
fn test_wrap_map_patch_lines_modified() {
    let mut wrap_map = WrapMap::new();
    let layout = NoOpLayout;

    // Initial sync
    let lines = vec!["Line 1".to_string(), "Line 2".to_string(), "Line 3".to_string()];
    wrap_map.sync(&lines, &layout, 800.0);

    // Modify line 1
    let patch = BufferPatch {
        start_row: 1,
        end_row: 2,
        kind: BufferPatchKind::LinesModified,
    };

    let new_lines = vec!["Line 1".to_string(), "Modified!".to_string(), "Line 3".to_string()];
    wrap_map.apply_patch(&patch, &new_lines, &layout, 800.0);

    // Verify only line 1 was re-wrapped
    assert_eq!(wrap_map.row_count(), 3);
}
```

## Success Criteria

- [x] `Buffer` tracks version, increments on every edit (already existed)
- [x] `EditorState` tracks `last_synced_version`
- [x] All patch types defined and documented (`display_map/patch.rs`)
- [x] `WrapMap` already uses `SumTree<WrapItem>` (no refactor needed)
- [x] `WrapMap::apply_patch()` implemented and tested (4 tests)
- [x] `BlockMap::apply_patch()` implemented (delegates to existing insert/remove)
- [x] Patches correctly represent all edit types (insert/delete/modify)
- [x] `DisplayMap::sync_incremental()` propagates patches through layers
- [x] `EditorState::sync_layout_incremental()` with version-skip optimization (5 tests)
- [x] Fixed SumTree `remove_range`/`replace_range` Bias bug for correct `[start,end)` semantics
- [x] All 350 lib tests pass (341 original + 9 new)
- [x] Committed: `50a39d6 feat(editor-core): implement DisplayMap incremental patch system`

## Next Steps

After completing this step:

- Step 4: Full integration of patches into `DisplayMap::sync_incremental()`
- Step 5: Replace `sync_layout()` calls with incremental version
- Step 6: Benchmarking and performance validation

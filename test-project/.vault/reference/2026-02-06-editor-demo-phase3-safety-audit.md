---
tags:
  - "#reference"
  - "#editor-demo"
date: 2026-02-06
related:
  - "[[2026-02-05-editor-demo-phase3-plan]]"
  - "[[2026-02-05-editor-demo-displaymap-reference]]"
  - "[[2026-02-05-editor-demo-core-reference]]"
  - "[[2026-02-05-editor-demo-architecture]]"
---

# Editor Demo Reference: Phase 3 Safety Audit

Safety audit of Phase 3 (Display Map Completeness) code changes across 2 commits:

- `afa78c2` -- InlayMap pass-through, TabMap tab expansion, BlockPlacement::Replace
- `07d2cdd` -- Wire DisplayMap::sync() to all layers

## Findings

### 1. No-Crash Policy -- PASS

Zero instances of `.unwrap()`, `.expect()`, `panic!()`, `unimplemented!()`, or `todo!()` in any production code across all 6 display map files:

- `inlay_map.rs` -- Clean
- `tab_map.rs` -- Clean
- `fold_map.rs` -- Clean
- `wrap_map.rs` -- Clean (pre-existing `unwrap_or(0)` at line 161 is safe)
- `block_map.rs` -- Clean
- `mod.rs` -- Clean

### 2. Unsafe Code -- PASS

No `unsafe` blocks anywhere in the display map directory. The parent crate `pp-editor-core` has pre-existing `unsafe` in `layout/cosmic.rs` only (outside Phase 3 scope).

### 3. Direct Indexing Audit

**`wrap_map.rs:159`** -- `item.wrap_points[wrap_idx - 1]`

- Guarded by `wrap_idx <= item.wrap_points.len()` at line 158, ensuring `wrap_idx - 1 < len`. Safe.

No other direct indexing in production code across the display map files. All iteration uses `for..in`, cursor-based tree traversal, or `.get()` patterns.

### 4. BlockPlacement::Replace Row Arithmetic -- NON-BLOCKING concern

**`block_map.rs:189`**:

```rust
let replaced_rows = end_row - start_row + 1;
```

If `end_row < start_row`, this would underflow (wrap to `u32::MAX`). There is no explicit guard at the `insert()` call site or `rebuild_from_blocks()`.

**Assessment:** Non-blocking because:

- `BlockPlacement::Replace { start_row, end_row }` is constructed by the caller. The API contract implies `start_row <= end_row`.
- In debug mode, Rust's arithmetic overflow detection would catch this.
- In release mode, the wraparound would produce an incorrect but not UB result (no unsafe).

**Recommendation:** Add a `debug_assert!(end_row >= start_row)` or saturating subtraction for defense-in-depth.

### 5. InlayMap Implementation -- PASS

**`inlay_map.rs`** (52 lines + 50 lines tests)

- Pure identity pass-through. `to_inlay_point()` and `from_inlay_point()` construct new points with same coordinates.
- `sync()` stores buffer line count. `row_count()` returns it.
- Struct is `Copy` and `Default` -- correct for a stateless pass-through.
- 5 unit tests covering identity mapping, round-trip, sync, origin point.
- Matches plan Task 1 specification exactly.

### 6. TabMap Implementation -- PASS

**`tab_map.rs`** (121 lines + 138 lines tests)

- Tab expansion algorithm iterates characters tracking visual column. Tab stops at `(visual_col / tab_size + 1) * tab_size`. Correct.
- `from_tab_point()` handles mid-tab snap correctly: if target visual column falls within a tab expansion, breaks to the tab character position.
- Identity pass-through methods (`to_tab_point_identity`, `from_tab_point_identity`) provided for call paths without line text access. Used in `DisplayMap::to_display_point()` with TODO comments.
- `sync()` accepts `fold_line_count` and `tab_size`. `row_count()` returns fold line count (tabs don't add rows).
- 11 unit tests covering: no-tabs identity, tab at start, tab mid-line, mid-tab snapping, round-trip, tab_size=8, multiple tabs, sync, identity pass-through, empty line.
- Matches plan Task 2 specification.

### 7. DisplayMap::sync() Pipeline -- PASS

**`mod.rs:155-186`**

Pipeline order: InlayMap -> FoldMap -> TabMap -> WrapMap -> BlockMap.

- InlayMap synced first with `line_count`.
- FoldMap: No explicit sync needed (folds are user-action-based). `tree_summary()` used to get fold row count.
- TabMap: synced with `fold_row_count` (falls back to `line_count` when no folds active). Correct fallback logic at line 175-176.
- WrapMap: synced with raw buffer lines. TODO comment notes it should receive post-fold lines for full correctness. Acceptable for demo.
- BlockMap: No sync needed (positioned by buffer row anchors).

**Signature change:** `sync()` now accepts `tab_size: u32` parameter. `EditorState::sync_layout()` delegates with default `tab_size=4`. `sync_layout_with_tab_size()` provides explicit control. Backward-compatible.

### 8. BlockPlacement::Replace -- PASS

**`block_map.rs`**

- New `Replace { start_row, end_row }` variant added to `BlockPlacement`.
- New `BlockItem::Replace { id, replaced_rows, height }` variant in the SumTree.
- `BlockSummary` for Replace: `buffer_rows = replaced_rows`, `display_rows = height`. Correctly accounts for hidden rows vs shown block height.
- `to_display_point()`: Points within replaced range map to the block's display row (line 305-306). Correct.
- `from_display_point()`: Replace block maps back to `start_buffer_row` with column 0 (line 345). Correct.
- `rebuild_from_blocks()`: Handles Replace by emitting neutral gap, then Replace item consuming `replaced_rows` buffer rows (lines 181-195).
- `all_blocks()`: Reconstructs Replace blocks from SumTree items, recovering `start_row` and `end_row` from cursor position and `replaced_rows` (lines 231-239).
- `Block::sort_key()`: Replace blocks sort by `start_row` with order 1 (between Above=0 and Below=2). Correct.
- 7 unit tests: basic replace, remove, combined with Above/Below, resize, multiple non-overlapping replaces.

### 9. Coordinate Round-Trip Through Full Pipeline -- PASS

**`mod.rs:196-237`**

- `to_display_point()`: Buffer -> Inlay -> Fold -> Tab(identity) -> Wrap -> Block. Each layer called correctly.
- `from_display_point()`: Block -> Wrap -> Tab(identity) -> Fold -> Inlay -> Buffer. Reverse order correct.
- `row_count()`: Chains wrap rows through block map. Correct.
- Integration test at line 279-301 verifies round-trip for all valid buffer points in a 4-line document.
- Integration test at line 303-325 verifies fold + block interaction.

### 10. SumTree Usage Correctness -- PASS

All SumTree operations use the established patterns:

- `cursor.seek()` with appropriate Bias
- `cursor.start_as::<Dim>()` for position tracking
- `cursor.item()` with `match` for type dispatch
- `cursor.next()` for iteration
- No direct tree manipulation outside `push()` and `new()`

Summary dimensions are consistent:

- `BlockSummary`: `buffer_rows` + `display_rows`
- `FoldSummary`: `input_rows` + `output_rows`
- `WrapSummary`: `tab_rows` + `wrap_rows`

### 11. Compilation Status -- PASS

`cargo check --package pp-editor-core --lib --bins --tests`: 0 errors, 1 warning (unused import in `decoration/bridge.rs` -- pre-existing, outside Phase 3 scope).

## Summary

| Domain | Verdict | Notes |
|--------|---------|-------|
| No-Crash Policy | PASS | Zero unwrap/expect/panic in production code |
| Unsafe Audit | PASS | No unsafe in display map |
| Memory Safety & Ownership | PASS | Value types, SumTree by-value, correct cursor patterns |
| Error Integrity | N/A | No fallible operations in coordinate mapping |
| Direct Indexing | PASS | Single instance guarded by bounds check |
| Replace Row Arithmetic | NON-BLOCKING | No guard on `end_row >= start_row`; debug overflow would catch |
| Pipeline Ordering | PASS | Correct layer ordering in sync and coordinate mapping |
| Plan Compliance | PASS | All 4 tasks implemented per specification |
| Test Coverage | PASS | 30+ new unit tests across all files |

**Overall: APPROVED -- no blocking issues.**

One non-blocking recommendation: add `debug_assert!(end_row >= start_row)` in `rebuild_from_blocks()` for Replace blocks.

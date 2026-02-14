---
tags:
  - "#reference"
  - "#displaymap"
date: 2026-02-04
related: []
---

# DisplayMap Implementation Audit: BlockMap & WrapMap

**Date:** 2026-02-04
**Status:** Audit Complete
**Target:** `crates/pp-editor-core/src/display_map/`

## Executive Summary

The current implementation of `DisplayMap` follows the correct architectural layering (Inlay -> Fold -> Tab -> Wrap -> Block) as seen in the reference implementation. However, the internal data structures are significantly simplified compared to the reference implementation's `SumTree`-based approach. While this simplification aids in rapid initial development, it introduces $O(N)$ and $O(L)$ performance bottlenecks for coordinate mapping which will become problematic for large files or many blocks.

## 1. BlockMap Review

### Current Approach: `Vec<Block>`

- **Storage:** Maintains a sorted `Vec` of `Block` structs.
- **Complexity:**
  - Insertion/Removal: $O(N)$ (due to `Vec::insert/remove` and binary search).
  - Mapping: $O(N)$ where $N$ is the number of blocks.

### Comparison with Reference Implementation

- **Data Structure:** The reference implementation uses a `SumTree<Transform>`.
- **Mapping:** The reference implementation achieves $O(\log N)$ mapping via tree traversal.
- **Capabilities:** The reference implementation supports `Replace` blocks (replacing a range of text) and `Near` blocks (inline/next to text). Our project only supports `Above` and `Below`.

### Findings

- **Live Preview Requirements:** Obsidian-style live preview often requires many blocks for various markdown elements (images, callouts, etc.). If a document has hundreds of such elements, the $O(N)$ mapping cost in `to_display_point` and `from_display_point` will impact UI responsiveness during scrolling and typing.
- **Correctness:** The current mapping logic correctly handles basic row-based offsets for `Above` and `Below` blocks.

## 2. WrapMap Review

### Current Approach: `Vec<Vec<u32>>`

- **Storage:** Stores wrap column indices for each line in a nested vector.
- **Complexity:**
  - `sync`: $O( ext{Total Chars})$ - clears and rebuilds the entire map on every sync.
  - Mapping: $O(L)$ where $L$ is the number of lines (due to linear iteration over previous lines' wrap counts).

### Comparison with Reference Implementation

- **Efficiency:** The reference implementation uses `SumTree` for $O(\log L)$ mapping.
- **Asynchrony:** The reference implementation performs wrapping in background tasks with an "interpolated" state for immediate UI feedback. Our project wraps synchronously.
- **Integration:** The reference implementation integrates directly with `gpui::LineWrapper`. Our project has a `NoOpLayout` placeholder and a manual `sync` call.

### Findings

- **Scalability:** The current `to_wrap_point` implementation is $O(L)$. For a 10,000-line file, every coordinate lookup will iterate through the wrap counts of up to 10,000 lines. This is a critical performance bottleneck.
- **Sufficiency:** `Vec<Vec<u32>>` is insufficient for a production-grade editor. It lacks incremental updates and efficient summarization.

## 3. Coordinate Mapping Analysis

- **Block Placement:** Our logic handles `Above` and `Below` by shifting display rows. This is sufficient for basic markdown blocks but doesn't handle blocks that might replace text (e.g., hiding markdown markers in live preview).
- **Correctness:**
  - `to_display_point`: Correctly increments row offsets.
  - `from_display_point`: Correctly identifies if a point is within a block and returns the `BlockId`.
  - `WrapMap` mapping: Correctly calculates row and column offsets but with poor performance.

## 4. Performance Implications

| Operation | Current (pp-editor-core) | Reference Implementation |
|-----------|--------------------------|---------------|
| `Buffer -> Display` | $O(N + L)$ | $O(\log N + \log L)$ |
| `Display -> Buffer` | $O(N + L)$ | $O(\log N + \log L)$ |
| `Map Update (Edit)` | $O( ext{Total Content})$ | $O(\log  ext{Document})$ |

$N$ = number of blocks, $L$ = number of lines.

## 5. Missing Execution Documents

Note: The following execution steps are missing from `.docs/exec/`:

- `01-initial-research`
- `02-architecture-design`
- `06-final-validation`

These should be backfilled if required by the project's documentation standards, though this audit focuses on the technical content of the code.

## Recommendations

1. **Adopt SumTree:** Reimplement both `BlockMap` and `WrapMap` using `SumTree` or a similar summarization data structure. This is the single most important change for performance.
2. **Incremental Updates:** Modify `WrapMap` to support incremental updates instead of full rebuilding.
3. **Background Wrapping:** Implement background wrapping logic similar to the reference implementation to prevent UI freezes on large edits or re-wraps.
4. **Support `Replace` Blocks:** Add `BlockPlacement::Replace` to `BlockMap` to support more advanced markdown live-preview features (like hiding syntax markers).
5. **Refine Column Mapping:** Ensure `WrapMap` correctly handles character-based column mapping (UTF-8/Graphemes) rather than just byte or simple char offsets.

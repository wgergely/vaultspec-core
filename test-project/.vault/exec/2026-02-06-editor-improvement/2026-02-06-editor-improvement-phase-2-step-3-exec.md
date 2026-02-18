---
tags:
  - "#exec"
  - "#uncategorized"
date: 2026-02-06
---
# Step 3: Build DisplayMap Structure - Confirmation

## Objective

To implement, or confirm the existence and proper structure of, the core layered `DisplayMap` for coordinating buffer-to-display transformations, adhering to the `Inlay -> Fold -> Tab -> Wrap -> Block` pipeline.

## Findings

A comprehensive review of the codebase, particularly `crates/pp-editor-core/src/display_map/mod.rs`, has revealed that the core `DisplayMap` layered structure is largely already implemented and correctly organized:

1. **`DisplayMap` Struct**: The `DisplayMap` struct (`crates/pp-editor-core/src/display_map/mod.rs`) is defined to contain instances of all the intended layered maps:
    * `inlay_map: inlay_map::InlayMap`
    * `fold_map: fold_map::FoldMap`
    * `tab_map: tab_map::TabMap`
    * `wrap_map: wrap_map::WrapMap`
    * `block_map: block_map::BlockMap`
    This aligns perfectly with the architectural goal of a layered `DisplayMap` as described in [[2026-02-04-adopt-zed-displaymap.md]].

2. **Coordinate Point Types**: All necessary intermediate coordinate point types (`BufferPoint`, `InlayPoint`, `FoldPoint`, `TabPoint`, `WrapPoint`, `DisplayPoint`) are already defined and used to facilitate transformations between layers.

3. **Transformation Pipeline**: The `DisplayMap` provides `to_display_point` and `from_display_point` methods that correctly chain through the various map layers, performing the necessary coordinate transformations in sequence (e.g., `Buffer -> Inlay -> Fold -> Tab -> Wrap -> Block` for `to_display_point`).

4. **Existing Layer Implementations**:
    * `BlockMap` (`block_map.rs`), `WrapMap` (`wrap_map.rs`), and `FoldMap` (`fold_map.rs`) are fully implemented and effectively utilize the `SumTree` for their respective coordinate transformations, as confirmed in Step 2.
    * `TabMap` (`tab_map.rs`) is also fully implemented and functions as a layer in the pipeline.
    * `InlayMap` (`inlay_map.rs`) exists as a pass-through (identity mapping) implementation. While not fully featured (it does not yet use a `SumTree` for complex inlay logic), its presence establishes the architectural placeholder as intended by the phased implementation plan outlined in [[2026-02-04-adopt-zed-displaymap.md]] (Phase 3 for InlayMap).

5. **`DisplayMap::sync` Method**: A `sync` method exists within `DisplayMap` to orchestrate the synchronization of its child maps.

## Conclusion

The core layered `DisplayMap` structure, including its constituent maps and the coordination of point transformations, is already established within the `pp-editor-core` crate. This effectively completes the objective of "building" this structure.

However, a critical observation is that many of the individual map layers' `sync` or update methods (e.g., in `BlockMap`, `WrapMap`, `FoldMap`) currently perform a full rebuild of their internal `SumTree`s rather than applying incremental changes. This is a known performance bottleneck, as highlighted in [[2026-02-06-incremental-layout-engine-design-adr.md]] and [[2026-02-06-editor-audit-reference.md]]. Addressing this inefficiency is the primary goal of the next phase: implementing the `DisplayMapPatch` system.

## Next Steps

Proceed to Step 4: Implement Patch system (Implement the incremental update logic using `DisplayMapPatch`).

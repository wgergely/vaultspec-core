---
step: 1
feature: "Incremental Layout Engine"
phase: "Phase 2"
task: "Design DisplayMap architecture and Patch system"
date: 2026-02-06
---

# Step 1: Design DisplayMap Architecture and Patch System

## Objective

To synthesize the design principles for the `DisplayMap` architecture and its associated `DisplayMapPatch` system, drawing from the provided ADRs and research documents, in preparation for implementation.

## Synthesis of Design Principles

### 1. The Core DisplayMap Structure

The `DisplayMap` will serve as the central data structure within `pp-editor-core` responsible for managing the visual representation of the document. It will internally manage various layers that transform the raw buffer content into what is presented to the user. Following Zed's layered approach outlined in [[2026-02-04-adopt-zed-displaymap.md]], these layers will include:

* **Inlay Map**: For handling inline decorations or virtual text (e.g., type hints).
* **Fold Map**: For collapsing and expanding sections of code. The audit [[docs/audit-pp-editor-markdown-features-2026-02-03.md]] highlighted that the logic for folding is currently missing, indicating this will be a future implementation phase for the `DisplayMap`.
* **Tab Map**: For handling tab character expansion.
* **Wrap Map**: For soft wrapping lines based on viewport width.
* **Block Map**: Crucially, for embedding custom UI elements or formatted content directly into the text flow. This is essential for features like Markdown Live Preview and addresses the "Layout Synchronization Issues for Custom Blocks" identified in [[2026-02-06-editor-audit-reference.md]].

The `DisplayMap` will maintain a consistent coordinate system, allowing for accurate mapping between buffer positions (raw text) and screen coordinates (rendered text).

### 2. Incremental Updates with DisplayMapPatch

As detailed in [[2026-02-06-incremental-layout-engine-design-adr.md]], the layout engine must be incremental. Changes to the document (e.g., text edits, style changes, block insertions/deletions) will generate `DisplayMapPatch` objects. These patches will represent localized modifications to the `DisplayMap`.

The `EditorState::sync_layout` function, currently a performance bottleneck due to full recalculations [[2026-02-06-editor-audit-reference.md]], will be refactored to:
    a.  Detect changes in the underlying text buffer.
    b.  Generate `DisplayMapPatch` objects based on these changes.
    c.  Apply `DisplayMapPatch` objects to the `DisplayMap` to update only the affected regions.
    d.  Efficiently notify the rendering pipeline of the updated regions for redraw.

### 3. SumTree for Efficient Metrics Management

A `SumTree` (or a similar data structure optimized for range queries and updates) will be integrated within the `DisplayMap` architecture. Its primary role, as emphasized in [[2026-02-06-incremental-layout-engine-research.md]], will be to:

* Store and manage layout-related metrics such as line heights, cumulative line heights, and block dimensions.
* Enable rapid identification of affected ranges when `DisplayMapPatch` objects are applied.
* Facilitate efficient mapping between buffer coordinates and display coordinates.

### 4. Integration with EditorState

The `DisplayMap` and its associated `SumTree` and `Patch` mechanisms will be integrated into `pp-editor-core`, likely as internal components of or closely associated with the `EditorState`. This ensures that the core editor logic can interact with and manage the visual layout efficiently.

### 5. Addressing Audit Findings during Implementation

While designing the `DisplayMap`, the following audit findings will be considered during implementation:

* **`unwrap()` calls**: The implementation of `DisplayMap` and its layers will strictly adhere to the "no-crash" policy, replacing `unwrap()` with robust error handling or sensible defaults.
* **`LayoutBuilder` style sorting issue**: The `DisplayMap`'s approach to text styling must resolve or work around the `LayoutBuilder`'s style sorting issue, ensuring correct application of text styles. It's plausible that the `DisplayMap`'s internal handling of styling will supersede the problematic parts of the existing `LayoutBuilder`.

## Next Steps

Proceed to Step 2: Implement SumTree for layout metrics.

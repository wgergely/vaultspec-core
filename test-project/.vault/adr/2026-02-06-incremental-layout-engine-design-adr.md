---
tags:
  - "#adr"
  - "#incremental-layout-engine"
date: 2026-02-06
related:
  - "[[2026-02-06-incremental-layout-engine-research]]"
  - "[[2026-02-06-editor-improvement-plan]]"
---

# Incremental Layout Engine Design: EditorState::sync_layout | (**Status:** Accepted)

## Problem Statement

The current `EditorState::sync_layout` function likely performs a full layout recalculation whenever the document content changes or the viewport is updated. This approach becomes a significant performance bottleneck for large documents, frequent real-time updates (e.g., typing, collaborative editing), and complex display features (e.g., markdown live preview). This leads to decreased responsiveness, a poor user experience, and limits the scalability of the editor.

## Considerations

To address the performance issues, the design for an incremental layout engine for `EditorState::sync_layout` will take into account the following key factors:

* **Leverage Zed's `DisplayMap` and `BlockMap` Concepts:** Adopt the architectural principles and benefits of Zed's proven text layout system.
* **Utilize `SumTree` or Similar Data Structure:** Employ a data structure optimized for efficient range queries and updates to manage layout metrics.
* **Support for Incremental Updates:** The system must efficiently handle various types of changes, including character insertions/deletions, line breaks, text style changes, and custom block modifications, by only re-computing affected regions.
* **Integration with Existing `EditorState`:** The new layout engine must seamlessly integrate with the current `EditorState` and its dependencies.
* **Performance for Large Documents:** Achieve substantial and measurable performance improvements when dealing with documents containing thousands or tens of thousands of lines.
* **Real-time Responsiveness:** Ensure that UI updates remain fluid and instantaneous during active editing sessions.
* **Markdown Live Preview Support:** The design must accommodate the dynamic insertion and layout of custom rendered blocks for features like live markdown preview.

## Constraints

The design and implementation will operate under the following constraints:

* **GPUI Framework Compatibility:** The solution must be fully compatible with and ideally leverage capabilities provided by the GPUI framework.
* **Measurable Performance Gains:** The implemented solution must demonstrate significant, quantifiable performance improvements compared to the current full recalculation approach.
* **Correctness and Stability:** The new layout engine must accurately represent the document and remain stable under all editing conditions, without introducing visual glitches or crashes.
* **Minimal Overhead:** Avoid introducing undue computational complexity or excessive memory overhead that could negate performance gains or lead to other issues.
* **Maintainability:** The resulting code should be well-structured, understandable, and maintainable.

## Implementation

The incremental layout engine for `EditorState::sync_layout` will be implemented with the following high-level approach:

1. **Introduce a `DisplayMap`-like Structure:** A new internal data structure, conceptually similar to Zed's `DisplayMap`, will be added to `EditorState`. This structure will be responsible for storing and managing the visual representation of the document, including visible lines, text properties, and the positions of custom blocks.
2. **Integrate a `SumTree` for Layout Metrics:** A `SumTree` (or a similar interval-tree-like structure) will be used to efficiently store and query layout-related metrics, such as line heights, cumulative line heights, and potentially block dimensions. This `SumTree` will allow for quick determination of visible ranges and the impact of localized changes.
3. **Refactor `EditorState::sync_layout` for Incremental Updates:** The `sync_layout` function will be modified to:
    * Compare the current document state with the previous state to identify changes (text edits, style changes, block insertions/deletions).
    * Use the `SumTree` to pinpoint the exact regions in the `DisplayMap` that are affected by these changes.
    * Recalculate layout data only for the affected regions, updating the `DisplayMap` and `SumTree` accordingly.
    * Efficiently notify the rendering pipeline about the updated regions for redraw.
4. **Implement `BlockMap`-like Functionality:** A dedicated mechanism within the `DisplayMap` or as a companion to it will be developed to manage and lay out custom blocks of content. This will involve:
    * Defining an interface for "blocks" that can be inserted into the text flow.
    * Ensuring these blocks are correctly positioned and sized during layout.
    * Handling the dynamic nature of blocks (e.g., markdown rendering changes).

## Rationale

This design choice is primarily driven by the insights gained from researching Zed's editor architecture:

* **Proven Model:** Zed's highly performant, incremental text layout system provides a robust and battle-tested model to emulate. Its success in handling large files and real-time collaboration demonstrates the effectiveness of `DisplayMap` and `SumTree` concepts.
* **Efficient Range Operations:** The `SumTree` data structure is uniquely suited for performing efficient range-based queries and updates, which are fundamental to incremental layout. This allows for precise identification and recalculation of only the affected parts of the layout, leading to significant performance gains over full recalculations.
* **Direct Addressing of Performance Bottlenecks:** By adopting these patterns, the core performance bottlenecks associated with `EditorState::sync_layout`'s full recalculation will be directly addressed, leading to a more responsive and scalable editor.
* **Foundation for Advanced Features:** An incremental layout engine is a prerequisite for advanced features such as sophisticated markdown live preview, where dynamic blocks of content need to be seamlessly integrated and efficiently updated.

## Consequences

### Positive Consequences

* **Significant Performance Improvement:** Expect substantial improvements in editor responsiveness, especially for large documents and complex editing operations.
* **Enhanced User Experience:** A smoother and more fluid editing experience, reducing perceived lag and improving overall productivity.
* **Scalability for Rich Content:** Provides a solid foundation for integrating and efficiently rendering rich content and dynamic blocks, crucial for features like markdown live preview.
* **Efficient Resource Utilization:** Reduces CPU cycles and potentially memory usage by avoiding unnecessary recalculations.

### Negative Consequences

* **Increased Code Complexity:** The implementation of `DisplayMap`-like structures and `SumTree` will introduce a significant amount of new, complex code into `EditorState` and related modules.
* **Higher Learning Curve:** Developers working on the layout engine will need to understand complex data structures and algorithms.
* **Potential for New Bugs:** Incremental updates can be challenging to implement correctly, with potential for off-by-one errors, visual glitches, or incorrect layout if not meticulously handled and tested.
* **Debugging Challenges:** Debugging issues within a complex incremental layout system can be more difficult than debugging a simpler, full-recalculation approach.
* **Initial Development Overhead:** The initial development and stabilization phase will require a considerable investment of time and effort.

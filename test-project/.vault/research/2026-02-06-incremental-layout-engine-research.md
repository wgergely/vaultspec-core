---
tags:
  - "#research"
  - "#incremental-layout-engine"
date: 2026-02-06
related:
  - "[[2026-02-06-editor-improvement-plan]]"
---

# Incremental Layout Engine Research: Zed's DisplayMap and BlockMap

This document details the research into incremental layout techniques, specifically focusing on Zed's `DisplayMap` and `BlockMap` architectures. The goal is to understand their core principles, data structures, and algorithms to inform the design and implementation of an incremental layout engine for `EditorState::sync_layout`. This research is crucial for improving the performance of the editor, particularly for large documents and real-time updates.

## Findings

### Overview of Zed's DisplayMap and BlockMap

Zed's text rendering and editing capabilities are built upon a sophisticated architecture that prioritizes efficiency and responsiveness, particularly through its `DisplayMap` and `BlockMap` components.

* **DisplayMap:** This is a core data structure that consolidates all information necessary for how a text buffer is presented to the user. It integrates diverse display-related aspects such as text folds, line wrapping, inlay hints, and custom content blocks. Essentially, `DisplayMap` constructs and manages the visual representation of the underlying document content.

* **BlockMap:** As a specialized part of the `DisplayMap`, the `BlockMap` specifically handles custom, embedded blocks of content. This includes elements like diagnostic messages or, crucially for our application, rendered markdown components (e.g., images, code blocks, mathematical equations) that need to be dynamically inserted and displayed within the text flow. Its role is vital for features requiring the insertion of non-textual or specially formatted content.

### Key Data Structures for Efficiency

The performance and responsiveness of Zed's editor are heavily reliant on its choice and application of fundamental data structures:

* **Rope-like Structure:** For representing the actual text content of a buffer in memory, Zed employs a data structure similar to a rope. This structure is optimized for efficient text manipulation operations, particularly insertions and deletions, which are frequent in a text editor and would be highly inefficient with simple contiguous arrays.

* **SumTree:** This is a pervasive and foundational data structure throughout Zed's architecture, utilized for various purposes including the `DisplayMap` itself, managing file lists, and handling diagnostics. `SumTree`s are exceptionally effective for performing rapid queries and updates over ranges of data. In the context of the `DisplayMap`, `SumTree` enables the editor to quickly identify and update only the specific portions of the display that have been affected by a change. This is critical for incremental layout, as it avoids the need to re-calculate and re-render the entire document for minor edits.

* **CRDT (Conflict-Free Replicated Data Type):** While less directly related to the layout engine itself, it's noteworthy that every buffer in Zed is implemented as a CRDT. This underpins Zed's collaborative editing features, ensuring that concurrent modifications from multiple users can be merged consistently and reliably, ultimately leading to an eventually consistent state across all collaborators.

### Incremental Layout Algorithms and Performance Considerations

The combination of the `DisplayMap` and the extensive use of `SumTree`s forms the basis for Zed's incremental layout approach. Although explicit "incremental layout algorithms" are not named as distinct entities in the research, the architectural design inherently supports incremental updates:

1. **Localized Updates:** When a change occurs (e.g., a character insertion, a line deletion), the `SumTree` allows for rapid identification of the affected range within the `DisplayMap`. This means that only the necessary parts of the display representation need to be invalidated and re-calculated, rather than processing the entire document.

2. **Minimizing Re-rendering:** By updating only the changed portions, Zed significantly minimizes the computational cost of re-rendering. This strategy is crucial for maintaining a fluid user experience, especially with large files, frequent edits, and complex display elements.

3. **Preserving Mental Map:** The incremental nature helps preserve the user's "mental map" of the document, as visual changes are localized and predictable.

### Adaptability to `EditorState::sync_layout`

The concepts derived from Zed's architecture are highly adaptable for enhancing our `EditorState::sync_layout` function:

* **Adopt SumTree for Line and Block Management:** Introducing a `SumTree` or a similar range-query-optimized data structure could replace or augment existing line and block management within `EditorState`. This would allow for efficient tracking of line metrics, block positions, and changes.
* **Decouple Layout from Full Document Scan:** The current `sync_layout` likely performs a full scan or re-layout. An incremental approach would involve:
  * Detecting changes in the underlying text buffer.
  * Mapping these changes to affected regions in the `DisplayMap` (our equivalent layout structure).
  * Using the `SumTree` to efficiently update only these affected regions, recalculating layout data (e.g., line heights, block positions) where necessary.
* **Integrate BlockMap-like functionality:** For markdown live preview, we would need a mechanism similar to `BlockMap` to manage the layout and rendering of custom UI elements or formatted content that break the linear text flow. This would involve injecting these blocks into the layout process and ensuring their positions are correctly maintained during incremental updates.
* **Performance Bottleneck Identification:** The research highlights that the key to performance is avoiding full recalculations. Therefore, the implementation should focus on minimizing the scope of layout updates to only what has changed.

This research confirms that a `SumTree`-based approach, integrated with a `DisplayMap`-like concept for managing visual representation and `BlockMap`-like functionality for custom content, is a viable and highly effective strategy for creating an incremental layout engine.

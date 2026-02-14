---
tags:
  - "#adr"
  - "#adopt-zed-displaymap"
date: 2026-02-04
related:
  - "[[2026-02-04-editor-text-layout]]"
  - "[[2026-02-04-implement-zed-displaymap-plan]]"
  - "[[2026-02-04-advanced-editor-synthesis]]"
---

Number: ADR-0003
Title: Adopt Reference-Style DisplayMap and GPUI Text Layout
Date: 2026-02-04
Status: Proposed

## Problem Statement

The current text layout implementation in `pp-editor-core` relies on a basic `TextLayout` trait implemented via `cosmic-text`. This abstraction lacks the capabilities required for:

1. **Advanced Coordinate Mapping:** Handling soft wraps, code folding, and expanding tabs in a way that maps correctly between buffer positions and screen coordinates.
2. **Rich Text Rendering:** Leveraging the high-performance text shaping and rendering capabilities of the GPUI framework (which powers our UI).
3. **Live Markdown Preview:** Inserting non-text elements (images, tables, headers) directly into the editor flow ("Obsidian-like" behavior) without breaking the buffer coordinate system.

## Considerations

- **Parity with Reference Codebase:** The reference implementation solves these exact problems using a layered `DisplayMap` (`Inlay` -> `Fold` -> `Tab` -> `Wrap` -> `Block`) and a tight integration with `gpui::TextSystem`.
- **Performance:** `gpui`'s text system is highly optimized for GPU rendering and integrates seamlessly with the rest of our UI stack.
- **Architecture Agnosticism:** `pp-editor-core` is designed to be framework-agnostic. We must avoid hard-coding `gpui` types deep into the core logic while still enabling them via traits.
- **Markdown Requirements:** The "Live Preview" feature necessitates a way to reserve vertical space for rendered blocks that exist logically at a single line in the buffer.

## Constraints

- **Existing Codebase:** `pp-editor-core` is already established; changes must be incremental or done via a clear refactor path.
- **GPUI Dependency:** `pp-ui-core` depends on `gpui`, but `pp-editor-core` currently keeps `gpui` optional or behind feature flags/traits.

## Implementation

1. **Refactor `TextLayout` Trait:** Update the `TextLayout` trait in `pp-editor-core` to accept `TextRun`s (styled ranges) and `FontId`s. This aligns the abstract interface with the capabilities of `gpui::TextSystem`.
2. **Implement `GpuiTextLayout`:** Create a new struct `GpuiTextLayout` in `pp-ui-core` (or a dedicated adapter crate) that implements the refactored `TextLayout` trait using `gpui::TextSystem`.
3. **Adopt `DisplayMap` Architecture:** Implement a simplified version of the reference implementation's `DisplayMap` hierarchy in `pp-editor-core`.
    - **Phase 1:** Implement `BlockMap` to handle "blocks" (essential for Markdown preview).
    - **Phase 2:** Implement `WrapMap` for soft wrapping.
    - **Phase 3:** Integrate `FoldMap` and `InlayMap` as needed.
4. **Markdown Blocks:** Use `BlockMap` to support "Preview Blocks" that render markdown elements (images, tables) in place.

## Rationale

Adopting the reference implementation's architecture (Hybrid Option C from research) provides the best balance of performance and capability.

- **Why `DisplayMap`?** It is a proven pattern for handling the complex coordinate transformations required by a modern code editor with folding and wrapping. `BlockMap` specifically solves the unique "Live Preview" layout challenge.
- **Why `GpuiTextLayout`?** It allows us to use the high-performance rendering engine we already have access to (via GPUI) without coupling the core editor logic directly to the framework.

## Consequences

- **Complexity:** The `DisplayMap` architecture is complex to implement and test. It introduces multiple coordinate spaces (`BufferPoint`, `FoldPoint`, `DisplayPoint`) that must be carefully managed.
- **Refactoring:** Significant changes to `pp-editor-core`'s layout handling will be required. Existing `cosmic-text` implementation may need to be maintained as a fallback or deprecated.
- **Dependency Management:** Care must be taken to ensure `pp-editor-core` remains testable without a full GPUI context (headless testing).

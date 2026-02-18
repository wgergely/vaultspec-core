---
tags:
  - "#research"
  - "#editor-text-layout"
date: 2026-02-04
related:
  - "[[2026-02-04-adopt-zed-displaymap]]"
  - "[[2026-02-04-implement-zed-displaymap-plan]]"
---

# Research: Editor Text Layout & Rendering

**Date:** 2026-02-04
**Topic:** Replicating the Reference Editor's Text Layout & Rendering Architecture
**Status:** In Progress

## Goal

Establish a robust text layout and rendering architecture for `pp-editor-core` that matches the reference editor's capabilities (performance, correctness, folding, wrapping) while supporting our specific requirement of Obsidian-like Live Markdown Preview.

## Related

- Audit: [[2026-02-04-text-layout-audit]]

## Context

- **Current State:** `pp-editor-core` uses `cosmic-text` for layout. It has a basic `TextLayout` trait. It does not yet have advanced coordinate mapping (soft wraps, folds).
- **Reference Codebase State:** Uses a layered `DisplayMap` for logic and `gpui::TextSystem` for rendering.
- **Requirement:** "Obsidian-like" means mixed height blocks (images, tables) and live formatting (bold/italic in place).

## Research Findings

### 1. The `DisplayMap` Necessity

The reference implementation's `DisplayMap` is not just "nice to have"; it is the engine that makes advanced editing possible.

- **Problem:** Buffer coordinates (Row 10) do not match Visual coordinates (Row 15) when soft wrapping or folding is active.
- **Solution:** A chain of coordinate transformers.
  - `WrapMap`: Handles soft wraps.
  - `FoldMap`: Handles collapsing ranges.
  - `BlockMap`: Handles inserting non-text elements (Essential for Markdown Preview!).

### 2. Layout Engine Abstraction

The reference codebase's `gpui` is tightly coupled to its `TextSystem`. However, our `pp-editor-core` aims to be framework-agnostic.

- **Challenge:** `cosmic-text` manages its own buffer/layout. `gpui` manages its own.
- **Approach:** The `TextLayout` trait in `pp-editor-core` should effectively be a "Line Shaper". It shouldn't manage the whole buffer state (that's `DisplayMap`'s job). It should just answer: "Given this string and these styles, what are the glyph positions and total size?"

### 3. Markdown Live Preview (`BlockMap`)

The reference implementation's `BlockMap` allows inserting "blocks" between lines. This is ideal for:

- Code block backgrounds (spanning full width).
- Image previews (taking up vertical space).
- Headers (variable height).

## Options

### Option A: Port `DisplayMap` Logic

Implement the `Inlay -> Fold -> Tab -> Wrap -> Block` stack in `pp-editor-core`.

- **Pros:** Full control, framework agnostic logic.
- **Cons:** High complexity to implement from scratch.
- **Mitigation:** We can start with just `WrapMap` and `BlockMap`.

### Option B: Use `cosmic-text`'s built-in features

`cosmic-text` has `Editor` and `Buffer` structs that handle some wrapping.

- **Pros:** Easier initial setup.
- **Cons:** Less flexible than the componentized `DisplayMap`. Harder to inject custom "Blocks" (images) into the middle of a `cosmic-text` buffer without hacking it.

### Option C: Hybrid

Use `DisplayMap` logic for structure, but delegate the "Line Measurement" to the `TextLayout` trait (which can be `cosmic-text` or `gpui`).

## Recommendation

**Option C (Hybrid).**

1. **Implement `DisplayMap` Lite:** Start building the coordinate mapping layers in `pp-editor-core`. Specifically `BlockMap` is critical for Markdown features.
2. **Refine `TextLayout` Trait:** Update it to support "Rich Text" (TextRuns) so it can handle syntax highlighting and formatting (bold/italic).
3. **Implement `GpuiTextLayout`:** Create the adapter in `pp-ui-core` that uses `gpui::TextSystem` to fulfil the `TextLayout` trait. This aligns us with the reference tech stack.

## Action Plan

1. Define the `TextLayout` trait to accept `TextRun`s (style ranges).
2. Create a `GpuiTextLayout` struct in `pp-ui-core` that implements this trait using `gpui`.
3. Design the `DisplayMap` structs (`BlockMap` first for Markdown support).

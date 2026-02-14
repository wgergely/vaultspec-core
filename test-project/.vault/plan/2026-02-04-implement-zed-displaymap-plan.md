---
tags:
  - "#plan"
  - "#implement-zed-displaymap"
date: 2026-02-04
related:
  - "[[2026-02-04-adopt-zed-displaymap]]"
  - "[[2026-02-04-editor-text-layout]]"
---

# Plan: Implement reference-style DisplayMap & Text Layout

Date: 2026-02-04
Task: Implement reference-style DisplayMap & Text Layout
Exec summary: `.docs/exec/2026-02-04-implement-zed-displaymap/summary.md`

## Brief

Adopting the reference implementation's "DisplayMap" architecture to handle complex text layout features (soft wrapping, folding) and specifically to enable "Obsidian-like" Live Preview via `BlockMap`. This also involves migrating the actual text rendering to `gpui`'s high-performance `TextSystem` via a refactored `TextLayout` trait.

## Goals

- Refactor `TextLayout` trait in `pp-editor-core` to support "Rich Text" (`TextRun`s) and style information.
- Implement `GpuiTextLayout` in `pp-ui-core` that implements the `TextLayout` trait using `gpui::TextSystem`.
- Implement `DisplayMap` architecture in `pp-editor-core` with an initial focus on `BlockMap` (for live preview blocks) and `WrapMap` (for soft wrapping).
- Ensure `pp-editor-core` remains framework-agnostic by using the `TextLayout` trait abstraction.

## Success Criteria

- `TextLayout` trait accepts `TextRun`s and returns formatted line metrics.
- `GpuiTextLayout` successfully renders text using `gpui` when used by the editor.
- `BlockMap` allows inserting "virtual" blocks (e.g., spacers for images) that are respected in the layout but exist at a single buffer point.
- `WrapMap` successfully handles soft-wrapping of long lines based on a viewport width.

# Steps

- Phase 1: Refactor TextLayout Trait - [[2026-02-04-adopt-zed-displaymap]] **COMPLETED**
  - Name: Define TextRun and FontId Types
  - Step summary: `.docs/exec/2026-02-04-implement-zed-displaymap/01-define-types.md`
  - Executing sub-agent: rust-executor-simple
  - References: [[2026-02-04-text-layout-audit]]
  
  - Name: Update TextLayout Trait Interface
  - Step summary: `.docs/exec/2026-02-04-implement-zed-displaymap/02-update-trait.md`
  - Executing sub-agent: rust-executor-standard
  - References: [[2026-02-04-adopt-zed-displaymap]]

- Phase 2: Implement GpuiTextLayout - [[2026-02-04-editor-text-layout]] **COMPLETED**
  - Name: Create GpuiTextLayout Struct
  - Step summary: `.docs/exec/2026-02-04-implement-zed-displaymap/03-create-gpuilayout.md`
  - Executing sub-agent: rust-executor-standard
  - References: [[2026-02-04-text-layout-audit]]

  - Name: Implement TextLayout for GpuiTextLayout
  - Step summary: `.docs/exec/2026-02-04-implement-zed-displaymap/04-implement-trait.md`
  - Executing sub-agent: rust-executor-complex
  - References: [[2026-02-04-text-layout-audit]]

- Phase 3: Implement DisplayMap & BlockMap - [[2026-02-04-text-layout-audit]] **COMPLETED**
  - Name: Scaffold DisplayMap Structure
  - Step summary: `.docs/exec/2026-02-04-implement-zed-displaymap/05-scaffold-displaymap.md`
  - Executing sub-agent: technical-auditor
  - References: [[2026-02-04-adopt-zed-displaymap]]

  - Name: Implement BlockMap Logic
  - Step summary: `.docs/exec/2026-02-04-implement-zed-displaymap/06-implement-blockmap.md`
  - Executing sub-agent: technical-auditor
  - References: [[2026-02-04-editor-text-layout]]

- Phase 4: Implement WrapMap - [[2026-02-04-text-layout-audit]] **COMPLETED**
  - Name: Implement WrapMap Logic
  - Step summary: `.docs/exec/2026-02-04-implement-zed-displaymap/07-implement-wrapmap.md`
  - Executing sub-agent: technical-auditor
  - References: [[2026-02-04-text-layout-audit]]

---
tags:
  - "#exec"
  - "#implement-zed-displaymap"
date: 2026-02-04
related:
  - "[[2026-02-04-implement-zed-displaymap-plan]]"
---

# implement-zed-displaymap

## Modified Files

- `crates/pp-ui-core/src/text.rs`: Created/Updated with `TextLayout` trait and related types.
- `crates/pp-ui-core/src/text/gpui.rs`: Created with `GpuiTextLayout` struct.
- `crates/pp-ui-core/src/lib.rs`: Registered `text` module and re-exported types.
- `crates/pp-editor-core/src/layout/mod.rs`: Updated to re-export types from `pp-ui-core`.

## Summary

- Created `GpuiTextLayout` struct in `pp-ui-core` to bridge the editor with GPUI's text system.
- Moved `TextLayout` trait and related data structures (`TextRun`, `GlyphPosition`, etc.) from `pp-editor-core` to `pp-ui-core` to resolve circular dependencies.
- Updated `pp-editor-core` to use the centralized text abstractions from `pp-ui-core`.
- Verified the changes with `cargo check`.

---
tags:
  - "#exec"
  - "#implement-zed-displaymap"
date: 2026-02-04
related:
  - "[[2026-02-04-implement-zed-displaymap-plan]]"
---

# implement-zed-displaymap

- **Status**: Completed (with API limitations fallback)
- **Modified Files**:
  - `crates/pp-ui-core/src/text/gpui.rs`

## Summary

Implemented `TextLayout` trait for `GpuiTextLayout`.
Due to visibility issues with `gpui::TextSystem::layout_line` and `shape_line` in the linked `gpui` version/configuration, a direct call to `gpui`'s layout engine was not possible from `pp-ui-core`.

Instead, I implemented a fallback layout mechanism using `gpui::TextSystem::advance` (which is public) to calculate character positions and metrics. `glyph_id` is set to 0 as `glyph_for_char` is not exposed.

This allows the editor to measure and layout text (calculate widths, heights, character positions) using `gpui`'s font system, which is sufficient for cursor movement and basic layout logic. Actual rendering will likely be handled by `gpui`'s `InteractiveText` or `StyledText` components which handle shaping internally.

## Key Changes

- Implemented `resolve_font` to map `AbsTextStyle` to `gpui::Font`.
- Implemented `measure_line` using `TextSystem::advance`.
- Implemented `layout_line` manually using `TextSystem::advance`.
- Implemented `char_position` and `index_at_position` using the manual layout logic.
- `rasterize_glyph` returns `None` as rasterization is handled by `gpui`.

## Deviations

- Did not use `gpui::TextSystem::layout_line` or `shape_line` directly due to `method not found` errors (likely internal/pub(crate) or visibility issue across crates).
- `LayoutLine` contains dummy glyph IDs (0). This is acceptable for layout calculations but not for custom rendering if relying on these IDs.

---
tags:
  - "#plan"
  - "#editor-demo"
date: 2026-02-05
related:
  - "[[2026-02-05-editor-demo-architecture]]"
  - "[[2026-02-05-editor-demo-research]]"
  - "[[2026-02-05-editor-demo-rendering-reference]]"
  - "[[2026-02-05-editor-demo-core-reference]]"
  - "[[2026-02-05-editor-demo-displaymap-reference]]"
  - "[[2026-02-04-displaymap-reference]]"
---

# Editor Demo Phase 1 Plan: Rendering Foundation

Make text visible. Replace colored rectangles with actual readable glyphs, display line numbers, and clip content correctly during scroll. This phase transforms the editor from a non-functional stub into a visually correct text display.

## Proposed Changes

The rendering pipeline in `pp-editor-main` is at 15% alignment with Zed's architecture ([[2026-02-05-editor-demo-rendering-reference]] Section 7). Three critical defects prevent any visual output:

1. **Text renders as colored rectangles.** `EditorElement::paint()` calls `TextRenderer::render_line()` which returns `Vec<RenderedGlyph>`, then paints each glyph as a solid `paint_quad(fill(...))`. The `atlas_region` is populated but never sampled -- GPUI's `paint_quad` does not accept texture coordinates. The entire custom `GlyphAtlas` + `BufferBelt` pipeline (463 lines in `text_renderer.rs`) must be replaced with GPUI's native `ShapedLine::paint()`.

2. **Gutter never paints.** `GutterRenderer` (459 lines in `gutter.rs`) collects `GutterCommand` structs via `render()`, but `EditorElement::paint()` only consumes `self.render_commands` from the decoration renderer -- it never reads gutter commands.

3. **No layout state between Element phases.** Both `RequestLayoutState` and `PrepaintState` are `()` (unit types). All work is crammed into `Render::render()` before the Element lifecycle or into `paint()` (too late for proper layout computation).

The ADR ([[2026-02-05-editor-demo-architecture]] Phase 1) prescribes five tasks to resolve these. Each is grounded in the rendering reference audit.

## Tasks

1. **Adopt 3-phase Element pattern with EditorLayout struct**

   - Step summary: `.docs/exec/2026-02-05-editor-demo/2026-02-05-editor-demo-phase1-step1.md`
   - Executing sub-agent: standard-executor
   - References: [[2026-02-05-editor-demo-rendering-reference]] Section 1, [[2026-02-05-editor-demo-architecture]] Phase 1 Task 2

   Sub-steps:
   1. Define `EditorRequestLayoutState` struct in `editor_element.rs` holding font metrics (font_id, font_size, line_height, em_width), gutter dimensions (computed from font metrics and line count), and editor width.
   2. Define `EditorLayout` struct (the PrepaintState) holding: `Vec<ShapedLine>` for text lines, `Vec<ShapedLine>` for line numbers, `Vec<SelectionRect>` for selection rectangles, `Vec<CursorLayout>` for cursor positions, editor/gutter/text-area `Hitbox` handles, visible row range, scroll position, and content bounds.
   3. Replace `type RequestLayoutState = ()` with the new `EditorRequestLayoutState` in the `Element` impl.
   4. Replace `type PrepaintState = ()` with the new `EditorLayout` in the `Element` impl.
   5. Move line shaping (currently in `paint()`) into `prepaint()`, populating the `EditorLayout` struct.
   6. Refactor `paint()` to consume `EditorLayout` exclusively -- no computation, only painting.
   7. Remove or reduce the work done in `Render::render()` on `EditorView` -- the pre-computation of `RenderItem`, `SelectionRect`, and `CursorVisual` should migrate to `prepaint()` where font metrics and layout data are available.

2. **Replace per-glyph paint_quad with GPUI ShapedLine::paint()**

   - Step summary: `.docs/exec/2026-02-05-editor-demo/2026-02-05-editor-demo-phase1-step2.md`
   - Executing sub-agent: standard-executor
   - References: [[2026-02-05-editor-demo-rendering-reference]] Section 2, [[2026-02-05-editor-demo-architecture]] Phase 1 Task 1

   Sub-steps:
   1. In `prepaint()`, use `window.text_system().shape_line()` to shape each visible text line. Each line requires: the text string, font_size, and a `Vec<TextRun>` specifying font, color, and decoration per character range. For now, use a single `TextRun` per line with the theme foreground color.
   2. Store the resulting `Vec<ShapedLine>` in `EditorLayout`.
   3. In `paint()`, call `ShapedLine::paint(origin, line_height, ...)` for each shaped line at its computed y-position.
   4. Remove the `TextRenderer` dependency from `EditorElement`. The `TextRenderer` struct, `GlyphAtlas`, `BufferBelt`, `RenderedGlyph`, and all associated types in `text_renderer.rs` are no longer needed by the rendering path. Mark them as deprecated or gate behind a feature flag -- do not delete yet since tests reference them.
   5. Remove the per-glyph `paint_quad(fill(...))` loop from `paint()` (lines 153-193 of current `editor_element.rs`).
   6. Update `EditorElement::new()` signature to no longer require `Arc<TextRenderer>`.

3. **Wire gutter painting into EditorElement::paint()**

   - Step summary: `.docs/exec/2026-02-05-editor-demo/2026-02-05-editor-demo-phase1-step3.md`
   - Executing sub-agent: standard-executor
   - References: [[2026-02-05-editor-demo-rendering-reference]] Section 3, [[2026-02-05-editor-demo-architecture]] Phase 1 Task 3

   Sub-steps:
   1. In `prepaint()`, compute `gutter_dimensions` from font metrics: `left_padding + (digit_count * em_width) + right_padding`. Use `GutterRenderer::calculate_gutter_width()` as a starting point but base it on the actual `em_width` from the resolved font, not approximated char widths.
   2. Shape each line number as a `ShapedLine` in `prepaint()` using the same `window.text_system().shape_line()` call. Right-align by computing `gutter_width - shaped_line.width - right_padding`. Store in `EditorLayout`.
   3. In `paint()`, paint the gutter background as a filled quad using the theme's `gutter.background` color.
   4. In `paint()`, paint the gutter separator line.
   5. In `paint()`, paint each shaped line number `ShapedLine` at its computed position.
   6. Highlight the current line number with the theme's `gutter.line_number_current` color.
   7. The existing `GutterRenderer` command-based approach is superseded. Mark it as deprecated but do not delete -- its tests validate gutter logic independently.

4. **Add content masking**

   - Step summary: `.docs/exec/2026-02-05-editor-demo/2026-02-05-editor-demo-phase1-step4.md`
   - Executing sub-agent: standard-executor
   - References: [[2026-02-05-editor-demo-rendering-reference]] Section 1, [[2026-02-05-editor-demo-architecture]] Phase 1 Task 4

   Sub-steps:
   1. In `paint()`, wrap all text-area painting operations in `window.with_content_mask(text_area_bounds, ...)` to clip content during scroll. The `text_area_bounds` is the editor bounds minus the gutter width.
   2. Wrap gutter painting in `window.with_content_mask(gutter_bounds, ...)` separately so gutter content clips to the gutter region.
   3. Remove the manual x/y clipping logic currently in `paint()` (lines 132-149 for selections, lines 167-179 for glyphs) -- content masking handles this.

5. **Register hitboxes in prepaint**

   - Step summary: `.docs/exec/2026-02-05-editor-demo/2026-02-05-editor-demo-phase1-step5.md`
   - Executing sub-agent: standard-executor
   - References: [[2026-02-05-editor-demo-rendering-reference]] Section 1, [[2026-02-05-editor-demo-architecture]] Phase 1 Task 5

   Sub-steps:
   1. In `prepaint()`, call `window.insert_hitbox(editor_bounds, false)` to register the full editor hitbox. Store the returned `HitboxId` in `EditorLayout`.
   2. Register a gutter hitbox: `window.insert_hitbox(gutter_bounds, false)`.
   3. Register a text-area hitbox: `window.insert_hitbox(text_area_bounds, false)`.
   4. Store all three `HitboxId`s in `EditorLayout` for use by Phase 2 mouse event handlers.
   5. Verify that the hitbox registration uses correct bounds (accounting for scroll offset and gutter width).

## Parallelization

- **Task 1 (3-phase pattern) must be completed first.** It defines the `EditorLayout` struct and restructures the Element lifecycle that all other tasks depend on.
- **Tasks 2 and 3 can proceed in parallel** after Task 1 is complete. They each populate different fields of `EditorLayout` (text lines vs line numbers) and paint to different regions (text area vs gutter).
- **Task 4 (content masking) depends on Tasks 2 and 3** since it wraps their paint calls.
- **Task 5 (hitboxes) can proceed in parallel with Tasks 2 and 3** since it only adds to `prepaint()` and `EditorLayout`.

Execution order: `1 -> (2 | 3 | 5) -> 4`

## Verification

### Success Criteria

1. **Text is readable.** Opening the demo example (`pp-editor-main/examples/demo.rs`) displays actual glyph-rendered text, not colored rectangles. Characters, ligatures, and Unicode content render correctly.
2. **Line numbers are visible.** The gutter displays right-aligned line numbers using the theme's line number color, with the current line highlighted.
3. **Scroll clipping works.** Scrolling does not cause text or line numbers to bleed outside the editor bounds.
4. **Hitboxes are registered.** Three hitboxes (editor, gutter, text-area) exist after prepaint. Verifiable by logging hitbox count or via GPUI inspector.
5. **Selection rectangles render correctly.** Existing selection rendering still works (painted after text, not as colored rectangles).
6. **Cursor renders.** The cursor bar is still visible at the correct position.
7. **No regressions.** Existing unit tests in `text_renderer.rs` and `gutter.rs` continue to pass (deprecated code is not deleted).
8. **`cargo check --all-targets` passes** for `pp-editor-main` and all dependent crates.

### Verification Method

- Run `cargo test -p pp-editor-main` to confirm no regressions.
- Run `cargo run --example demo -p pp-editor-main` to visually confirm text rendering, gutter, and scroll clipping.
- The most critical validation is **visual**: text must be human-readable, not colored boxes. This cannot be verified by unit tests alone. An integration test that checks `ShapedLine` output dimensions (non-zero width for non-empty text) provides a proxy.

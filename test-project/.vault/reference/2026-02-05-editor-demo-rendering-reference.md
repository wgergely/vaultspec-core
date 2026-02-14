---
tags:
  - "#reference"
  - "#editor-demo"
date: 2026-02-05
related:
  - "[[2026-02-05-editor-demo-research]]"
  - "[[2026-02-04-rendering-audit]]"
  - "[[2026-02-04-text-layout-audit]]"
  - "[[2026-02-04-glyph-atlas-audit]]"
---

# Rendering Pipeline Reference: pp-editor-main vs Zed element.rs

Crate(s): `pp-editor-main`, `ref/zed/crates/editor`, `ref/zed/crates/gpui`
File(s):

- `Y:\code\popup-prompt-worktrees\main\crates\pp-editor-main\src\editor_element.rs` (our EditorElement, 253 lines)
- `Y:\code\popup-prompt-worktrees\main\crates\pp-editor-main\src\editor_view.rs` (our EditorView + Render, 457 lines)
- `Y:\code\popup-prompt-worktrees\main\crates\pp-editor-main\src\text_renderer.rs` (our TextRenderer/GlyphAtlas, 463 lines)
- `Y:\code\popup-prompt-worktrees\main\crates\pp-editor-main\src\gutter.rs` (our GutterRenderer, 459 lines)
- `Y:\code\popup-prompt-worktrees\main\crates\pp-editor-main\src\decoration_views.rs` (our decoration renderer, 552 lines)
- `Y:\code\popup-prompt-worktrees\main\crates\pp-editor-main\src\blocks\mod.rs` (our block system, 54 lines)
- `Y:\code\popup-prompt-worktrees\main\ref\zed\crates\editor\src\element.rs` (Zed EditorElement, 11900+ lines)
- `Y:\code\popup-prompt-worktrees\main\ref\zed\crates\gpui\src\text_system.rs` (Zed TextSystem)

---

## 1. Element Trait Implementation

### Zed Architecture (element.rs:9388-10886)

Zed's `EditorElement` implements the three-phase GPUI Element lifecycle:

**Phase 1 -- `request_layout`** (line 9388):

- Determines editor sizing based on `EditorMode` (SingleLine, AutoHeight, Full, Minimap).
- For `AutoHeight`, uses `window.request_measured_layout()` with a closure that computes layout dynamically.
- For `Full`, computes scroll height from `snapshot.max_point().row()`.
- Sets `rem_size` context for consistent rem-based sizing.
- Returns `EditorRequestLayoutState::default()` (empty state).

**Phase 2 -- `prepaint`** (line 9463):

- This is the **heavyweight phase** (~1350 lines of logic).
- Takes an `EditorSnapshot` for immutable read access.
- Resolves font metrics: `font_id`, `font_size`, `line_height`, `em_width`, `em_advance`.
- Computes `gutter_dimensions` from snapshot.
- Computes `editor_width = text_width - gutter_margin - 2*em_width - right_margin`.
- Configures soft wrap width based on mode.
- Inserts three hitboxes: `hitbox` (whole editor), `gutter_hitbox`, `text_hitbox`.
- Computes visible row range: `start_row..end_row` from scroll position + clipped bounds.
- Calls `layout_selections()` -> selections, active_rows, newest_selection_head.
- Calls `layout_line_numbers()` -> line number shaped text.
- Calls `layout_lines()` -> `Vec<LineWithInvisibles>` using `snapshot.highlighted_chunks()`.
- Calls `render_blocks()` -> block elements with sizes and positions.
- Calls `prepaint_lines()` -> positions line elements.
- Builds a comprehensive `EditorLayout` struct (~40 fields) passed to paint.

**Phase 3 -- `paint`** (line 10814):

- Sets key context, input handler, registers actions and key listeners.
- Calls painting sub-methods in strict order:
  1. `paint_mouse_listeners` -- event handlers
  2. `paint_background` -- fill editor background
  3. `paint_indent_guides` -- vertical indent guides
  4. `paint_blamed_display_rows` -- git blame
  5. `paint_line_numbers` -- gutter line numbers
  6. `paint_text` -- text content (which internally calls):
     - `paint_lines_background` -- line highlight backgrounds
     - `paint_highlights` -- selection/search highlights
     - `paint_document_colors` -- inline color swatches
     - `paint_lines` -- actual text glyphs
     - `paint_redactions` -- redacted ranges
     - `paint_cursors` -- cursor shapes
     - `paint_inline_diagnostics`
     - `paint_inline_blame`
     - `paint_inline_code_actions`
     - `paint_diff_hunk_controls`
     - crease trailers
  7. `paint_gutter_highlights`
  8. `paint_gutter_indicators` -- fold toggles, breakpoints, test indicators
  9. `paint_blocks` -- custom block elements
  10. `paint_sticky_headers`
  11. `paint_minimap`
  12. `paint_scrollbars`
  13. `paint_edit_prediction_popover`
  14. `paint_mouse_context_menu`

### Our Architecture (editor_element.rs:1-253, editor_view.rs:1-457)

Our implementation is split between `EditorView` (Render trait) and `EditorElement` (Element trait):

**EditorView::render** (editor_view.rs:213-308):

- Snapshots data from model (`model.read(cx).clone()`).
- Calls `prepare_render_items_static()` -- iterates visible rows from display_map, produces `Vec<RenderItem>` (Text or Block).
- Computes selection rects using `calculate_selection_rects_static()`.
- Computes cursor visual using `calculate_cursor_visual_static()`.
- Wraps everything in `gpui::div().track_focus().child(EditorElement::new(...))`.

**EditorElement** (editor_element.rs:53-253):

- `RequestLayoutState = ()`, `PrepaintState = ()` -- no intermediate state.
- `request_layout`: Only calls `window.request_layout(Style::default())` and requests layout for Block elements.
- `prepaint`: Only prepaint blocks at calculated positions.
- `paint`: Single method paints everything sequentially:
  1. `paint_commands` -- decoration render commands (FillRect, StrokeRect)
  2. Selection rectangles via `window.paint_quad(fill(...))`
  3. Text/Block items: text via `TextRenderer::render_line()` + per-glyph `paint_quad`, blocks via `element.paint()`
  4. Cursors via `paint_quad`

### Gap Analysis

| Aspect | Zed | Ours | Gap Severity |
|--------|-----|------|--------------|
| Layout state | Rich `EditorLayout` (~40 fields) | Unit types `()` | **CRITICAL** |
| Prepaint work | Font resolution, selection layout, line shaping, block rendering | Block positioning only | **CRITICAL** |
| Hitbox registration | 3 hitboxes (editor, gutter, text) | None | **HIGH** |
| Content masking | `window.with_content_mask()` wraps all phases | None | **HIGH** |
| Text rendering | Uses GPUI `shape_line` -> `ShapedLine.paint()` with native platform text | Custom `TextRenderer.render_line()` -> per-glyph `paint_quad` (colored rectangles) | **CRITICAL** |
| Paint order | 14+ sub-paint methods with strict layering | Single flat paint method | **MEDIUM** |
| Rem-based sizing | `window.with_rem_size()` context | Fixed pixel values | **MEDIUM** |
| Scroll computation | Fractional scroll position with overscroll modes | Direct pixel offset | **MEDIUM** |

---

## 2. Text Rendering

### Zed Text System (text_system.rs:54-560+)

Zed delegates all text work to GPUI's `TextSystem`:

- **Font resolution**: `TextSystem` wraps a `PlatformTextSystem` (per-OS: CoreText, DirectWrite, FreeType). Font IDs resolved once and cached.
- **Line shaping**: `WindowTextSystem::shape_line(text, font_size, runs, force_width)` returns a `ShapedLine` with positioned glyphs, widths, decoration runs. Uses `LineLayoutCache` for cross-frame caching.
- **Glyph rasterization**: `rasterize_glyph(RenderGlyphParams)` produces pixel data. Cached in atlas by the platform layer.
- **Painting**: `ShapedLine::paint(origin, line_height, align, ...)` draws glyphs using native GPU paths. No per-glyph quad emission.
- **Line wrapping**: `LineWrapper` does soft wrapping with glyph-aware boundaries.
- **Styled runs**: `TextRun` carries font, color, underline, strikethrough, background per-character-range.

### Our Text System (text_renderer.rs:1-423)

- **Font resolution**: `CosmicTextLayout` wraps cosmic-text for shaping. Single `FontConfig` at creation.
- **Line shaping**: `TextLayout::layout_line(text, styles, width)` produces `LayoutResult { glyphs, height, width }`.
- **Glyph atlas**: Custom `GlyphAtlas` with triple-atlas strategy (Monochrome, Subpixel, Polychrome). Row-based allocator with configurable max size (2048x2048).
- **Staging**: `BufferBelt` queues `PendingUpload` data for GPU upload. `before_frame()` flushes uploads.
- **Painting**: `render_line()` returns `Vec<RenderedGlyph>` which EditorElement paints as **colored rectangles** via `paint_quad(fill(...))`.

### Gap Analysis

| Aspect | Zed | Ours | Gap Severity |
|--------|-----|------|--------------|
| Text shaping | Platform-native (CoreText/DW/FreeType) via GPUI | cosmic-text | OK (cosmic-text is capable) |
| Glyph painting | Native GPU glyph rendering via ShapedLine.paint() | Per-glyph colored quad rectangles | **CRITICAL** -- glyphs render as colored boxes, not actual text |
| Atlas caching | Managed by GPUI platform layer | Custom triple-atlas with manual allocation | **MEDIUM** -- correct architecture but disconnected from GPUI render path |
| Line layout cache | `LineLayoutCache` with frame-based invalidation | None -- layouts recomputed every frame | **HIGH** |
| Styled runs | TextRun with per-range font/color/decoration | Single color per line | **HIGH** |
| Subpixel rendering | Platform-specific subpixel AA | Subpixel variant in atlas key, but not connected | **HIGH** |

**Critical Issue**: Our `EditorElement::paint()` calls `self.text_renderer.render_line()` then paints each glyph as a solid `paint_quad(fill(...))`. This means glyphs appear as colored rectangles, not actual letter shapes. The `atlas_region` is populated but never used to sample texture data -- the GPUI `paint_quad` API doesn't accept texture coordinates.

---

## 3. Gutter Rendering

### Zed Gutter (element.rs:3411-3490, 6004-6057)

- **GutterDimensions**: Computed from font metrics: `left_padding + line_number_width + right_padding + fold_area_width + git_gutter_width`.
- **Layout phase** (`layout_line_numbers`, line 3411): Shapes each line number as a `ShapedLine` using `shape_line_number()`. Supports relative line numbers, active row highlighting, diff status coloring. Creates per-line hitboxes for interaction.
- **Paint phase** (`paint_line_numbers`, line 6004): Paints shaped line numbers at computed origins. Handles hover state (re-shapes with hover color). Sets cursor style (IBeam for singleton, PointingHand for multibuffer).
- **Gutter indicators** (`paint_gutter_indicators`, line 6240): Paints fold/crease toggles, breakpoints, test indicators, expand buttons -- all as interactive elements with hitboxes.
- **Gutter diff hunks** (`paint_gutter_diff_hunks`, line 6059): Paints colored bars for git diff status in gutter margin.

### Our Gutter (gutter.rs:1-459)

- **GutterRenderer**: Collects `GutterCommand` variants (Background, LineNumber, Separator, FoldIndicator).
- **prepare_items**: Iterates visible lines, creates `GutterItem` structs with fold state from `FoldingSystem`.
- **render**: Calls render_background, render_separator, render_line_numbers, render_fold_indicators.
- **Line numbers**: Right-aligned text using character width approximation (`text.len() * Size::SM.px()`). Supports current-line highlighting.
- **Commands are collected but never painted**: The `GutterRenderer` produces `GutterCommand` structs, but `EditorElement::paint()` only paints `self.render_commands` from `decoration_renderer`, not gutter commands.

### Gap Analysis

| Aspect | Zed | Ours | Gap Severity |
|--------|-----|------|--------------|
| Line number shaping | ShapedLine via TextSystem | String + approximated width | **HIGH** |
| Line number painting | Native text paint with hitboxes | Commands collected but **never painted** | **CRITICAL** |
| Gutter dimensions | Font-metric-based (padding + number width + fold + git) | Fixed `settings.gutter_width` | **HIGH** |
| Fold toggles | Interactive elements with hitboxes | Command-based stubs | **HIGH** |
| Git gutter | Colored diff bars | Not implemented | **MEDIUM** |
| Relative line numbers | Full support | Not implemented | **LOW** |
| Gutter interactions | Per-line hitboxes, hover states, click handlers | None | **HIGH** |

---

## 4. Cursor and Selection Painting

### Zed Cursors (element.rs:1729-1810, 11739-11875)

- **CursorLayout struct** (line 11739): `origin`, `block_width`, `line_height`, `color` (Hsla), `shape` (Bar/Block/Hollow/Underline), `block_text` (ShapedLine for block cursor content), `cursor_name` (collaboration label).
- **Cursor shapes**:
  - Bar: 2px wide, full line height
  - Block: full character width, full line height, can show text underneath
  - Hollow: outline of block
  - Underline: full character width, 2px tall at line bottom
- **Painting**: `CursorLayout::paint()` draws fill or outline quad, then optional block_text, then optional cursor_name label.
- **Blinking**: Controlled by `CURSORS_VISIBLE_FOR` timer in editor state. Element reads `cursor_visible` flag during prepaint to decide which cursors to include in `visible_cursors`.

### Zed Selections (element.rs:1539-1727, 6422-6468)

- **SelectionLayout struct** (line 114): `head`, `cursor_shape`, `is_newest`, `is_local`, `range`, `active_rows`, `user_name`.
- **Layout phase** (`layout_selections`): Creates SelectionLayout for each selection, computes active rows, handles remote collaborator selections with player colors.
- **Paint phase** (`paint_highlights`): Uses `paint_highlighted_range()` to draw selection backgrounds with corner radius and line-end overshoot. Supports rounded selections (configurable).
- **Multi-cursor**: Full support for multiple selections, each with its own cursor and selection range.

### Our Cursors and Selections (editor_view.rs:274-291, editor_element.rs:202-210)

- **CursorVisual struct**: `x`, `y`, `width`, `height`, `visible`. Single shape only (bar-like).
- **Cursor painting**: Solid yellow `paint_quad(fill(...))`. Fixed width `Size::XS.px() * 0.5`. No blinking, no block cursor, no hollow cursor, no cursor name.
- **Selection painting**: `SelectionRect` with manual clipping to gutter edge and viewport. Hardcoded blue color `Rgba { r: 0.2, g: 0.4, b: 0.8, a: 0.3 }`. No corner radius.
- **Selection computation**: `calculate_selection_rects_static()` uses monospace char_width approximation (`font_size * 0.6`).

### Gap Analysis

| Aspect | Zed | Ours | Gap Severity |
|--------|-----|------|--------------|
| Cursor shapes | 4 shapes (Bar/Block/Hollow/Underline) | 1 shape (fixed-width bar) | **HIGH** |
| Cursor blinking | Timer-based visibility toggle | No blinking | **MEDIUM** |
| Cursor color | Theme-derived Hsla per player | Hardcoded yellow | **MEDIUM** |
| Block cursor text | Renders character under cursor | Not supported | **HIGH** |
| Cursor name labels | Collaboration user names | Not supported | **LOW** (collab feature) |
| Selection highlights | Rounded corners, per-player colors | Flat rectangles, hardcoded blue | **MEDIUM** |
| Multi-cursor | Full multi-selection support | Single cursor only | **HIGH** |
| Selection clipping | Content mask via GPUI | Manual x-axis clipping to gutter | **MEDIUM** |

---

## 5. Block Rendering

### Zed Blocks (element.rs:4096-4295, 7412-7448)

- **Block types**: Fixed, Flex, Sticky -- each with different width calculation.
- **render_blocks()** (line 4096): Partitions blocks into fixed vs non-fixed. Renders each via `render_block()` which produces `(AnyElement, Size, DisplayRow, x_offset)`. Tracks resized blocks. Fixed blocks use `MinContent` width; Flex blocks use max of editor width and scroll width.
- **BlockLayout struct** (line 11692): `id`, `x_offset`, `row`, `element`, `available_space`, `style`, `overlaps_gutter`, `is_buffer_header`.
- **paint_blocks()** (line 7412): Paints blocks in a dedicated `"blocks"` element namespace. Positions each block at its computed origin with scroll offset.
- **Block context**: Blocks receive full editor context including selections, buffer IDs, line layouts. Header blocks get special treatment (excerpt headers, buffer headers).

### Our Blocks (blocks/mod.rs:1-54, editor_element.rs:69-105, 195-198)

- **CustomBlock struct**: `id` (BlockId) + `render` (Arc closure -> AnyElement).
- **BlockContext**: `window`, `app`, `theme`, `block_id`.
- **Layout**: In `request_layout`, iterates RenderItems and calls `element.request_layout()` for Block variants.
- **Prepaint**: Positions blocks at `(gutter_width + x, row_y)` with `prepaint_as_root()`.
- **Paint**: Simple `element.paint()` call.
- **Block types**: Only one type (custom). No Fixed/Flex/Sticky distinction.

### Gap Analysis

| Aspect | Zed | Ours | Gap Severity |
|--------|-----|------|--------------|
| Block styles | Fixed/Flex/Sticky with different width rules | Single style | **MEDIUM** |
| Block width | Computed from editor width, scroll width, gutter | Fixed to content_width | **MEDIUM** |
| Block resize | Dynamic resize tracking with HashMap | Not supported | **MEDIUM** |
| Block rendering context | Full editor context (selections, buffers, line layouts) | Minimal (window, app, theme, id) | **MEDIUM** |
| Element namespace | Blocks in dedicated namespace | No namespace | **LOW** |
| Buffer/excerpt headers | Full header block support | Not applicable (single buffer) | **LOW** |
| Block focus | FocusedBlock tracking | Not supported | **MEDIUM** |

---

## 6. Layout Cache

### Zed Layout Caching

Zed uses multiple layers of caching:

1. **LineLayoutCache** (in WindowTextSystem): Frame-based cache for shaped lines. `layout_index()` / `reuse_layouts()` / `truncate_layouts()` manage cache generations. Lines shaped in one frame can be reused in the next if text hasn't changed.
2. **EditorSnapshot**: Immutable snapshot taken once per prepaint. Contains display_map state, buffer state, all transforms. No re-computation during rendering.
3. **PositionMap** (line 11588): Stores all computed layout data: `line_layouts`, `scroll_position`, `em_width`, hitboxes, visible row range. Built in prepaint, consumed in paint.
4. **GutterDimensions**: Cached on Editor struct (`editor.gutter_dimensions`), updated only when layout changes.

### Our Layout Caching (editor_view.rs:88-162)

- **LayoutCache struct**: Stores `line_heights`, `line_y_positions`, `content_height`, `max_line_width`, `buffer_version`, `valid` flag.
- **Invalidation**: `invalidate()` sets `valid = false`. `is_valid(buffer_version)` checks version.
- **Update**: `update(line_count, line_height, buffer_version)` recomputes all positions from scratch.
- **Usage**: `layout_cache.set_max_line_width()` called in render, but `line_y()` and `content_height()` are never called in the rendering path.

### Gap Analysis

| Aspect | Zed | Ours | Gap Severity |
|--------|-----|------|--------------|
| Line shape caching | Frame-based LineLayoutCache with reuse | None -- re-shapes every frame | **HIGH** |
| Snapshot immutability | Single snapshot per prepaint | Model cloned every render | **MEDIUM** |
| Position map | Rich struct with all layout data | Unit type () for prepaint state | **HIGH** |
| Cache invalidation | Version-based + frame generation | Version-based but cache is unused | **HIGH** |
| Gutter dimension caching | Cached on Editor, updated on change | Fixed settings value | **MEDIUM** |

---

## 7. Summary of Critical Gaps

### Must-Fix for Demo Functionality

1. **Text is painted as colored rectangles, not glyphs.** The `TextRenderer` produces `RenderedGlyph` structs that are drawn with `paint_quad(fill(...))`. This means the editor displays colored boxes instead of readable text. Must use GPUI's `ShapedLine::paint()` or equivalent.

2. **Gutter never paints.** `GutterRenderer` collects commands but `EditorElement::paint()` does not consume them. Line numbers are invisible.

3. **No layout state passed between phases.** `RequestLayoutState = ()` and `PrepaintState = ()` means all work is done in `Render::render()` (before the Element lifecycle) or in `paint()` (too late for proper layout). Should use prepaint to compute positions and pass a rich layout struct.

4. **No hitboxes.** Without hitboxes for gutter, text area, and individual elements, mouse interaction cannot work.

5. **No content masking.** Without `window.with_content_mask()`, content bleeds outside editor bounds during scrolling.

### Important but Not Blocking Demo

6. **Single cursor shape only.** Need at least Bar and Block for vim mode.
7. **Hardcoded colors everywhere.** Should derive from `EditorTheme`.
8. **No line layout caching.** Performance will degrade on large files.
9. **Monospace char_width approximation.** Works for demo but breaks with proportional fonts or ligatures.
10. **No scroll overscroll modes.** Missing scroll-beyond-last-line configuration.

### Architecture Recommendations

- **Adopt Zed's three-phase pattern**: Move line shaping and position computation to `prepaint`, store in a rich `EditorLayout`-like struct, consume in `paint`.
- **Use GPUI text system directly**: Replace per-glyph `paint_quad` with `ShapedLine::paint()`. This is the single highest-impact change.
- **Wire gutter rendering into paint**: Either paint gutter commands in `EditorElement::paint()` or restructure to use GPUI text painting for line numbers.
- **Add hitboxes for gutter and text areas**: Required for any mouse interaction.
- **Add content masking**: Required for correct scroll clipping.

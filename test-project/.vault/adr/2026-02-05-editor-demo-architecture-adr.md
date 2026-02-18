---
tags:
  - "#adr"
  - "#editor-demo"
date: 2026-02-05
related:
  - "[[2026-02-05-editor-demo-research]]"
  - "[[2026-02-05-editor-demo-core-reference]]"
  - "[[2026-02-05-editor-demo-events-reference]]"
  - "[[2026-02-05-editor-demo-rendering-reference]]"
  - "[[2026-02-05-editor-demo-displaymap-reference]]"
  - "[[2026-02-04-displaymap-reference]]"
  - "[[2026-02-04-editor-event-handling]]"
---

# Editor Demo ADR: Interactive Full-Featured Editor Stub | (**Status:** Accepted)

## Problem Statement

The editor crate ecosystem (pp-editor-core, pp-editor-events, pp-editor-main) has ~14,250 lines of code across 3 crates with solid architectural foundations, but no unified interactive demo that exercises all subsystems together. A cross-reference audit against Zed's editor backend reveals critical gaps that prevent the editor from functioning as an interactive application: text renders as colored rectangles instead of glyphs, the gutter never paints, no hitboxes exist for mouse interaction, and the IME/input pipeline is disconnected from the buffer.

An interactive, full-featured editor demo is required as a validation milestone before integration testing.

## Considerations

Four audit domains were evaluated against Zed's production editor:

### Core State (32% aligned)

- Buffer architecture (Ropey) is correct for our scope -- no CRDT needed
- Single offset-based cursor works for demo; anchor-based positioning is a future concern
- Undo/redo lacks transaction grouping (typing "Hello" = 5 undo entries) and selection restore
- Command dispatch via match statements is acceptable for demo

### Event Handling (70% aligned)

- Hit testing algorithm is identical to Zed's
- Action system uses GPUI's `actions!()` macro directly
- Focus system correctly delegates to GPUI with enhancements (FocusRestorer, FocusHistory)
- **Blocker**: EntityInputHandler not implemented -- IME/platform input won't reach the editor
- **Blocker**: `replace_text_in_range` is a stub -- no buffer write access from input handler
- Missing: click count detection, keystroke prefix replay, auto-scroll during drag

### Rendering Pipeline (15% aligned -- most critical)

- Text paints as colored rectangles via `paint_quad(fill(...))` instead of actual glyphs
- Gutter commands are collected but never consumed by `EditorElement::paint()`
- No layout state between Element phases (`RequestLayoutState = ()`, `PrepaintState = ()`)
- No hitboxes registered -- mouse interaction cannot work
- No content masking -- content bleeds during scroll
- Zed's element.rs is 11,900+ lines with ~40-field EditorLayout; ours is 253 lines with unit state

### Display Map Pipeline (32% aligned)

- Layer ordering is identical to Zed (Inlay -> Fold -> Tab -> Wrap -> Block)
- FoldMap, WrapMap, BlockMap all use SumTree correctly
- InlayMap and TabMap are empty stubs
- No snapshot architecture (mutable state read during render)
- No edit propagation chain (full rebuild on every change)
- SumTree missing `slice()`/`append()`/`suffix()` -- blocks incremental updates

## Constraints

1. **Demo scope**: Must render readable text, accept keyboard input, display selections, show line numbers, and support basic scrolling. Does not need: multi-cursor, collaboration, LSP integration, or async wrapping.
2. **GPUI dependency**: Must use GPUI's text system (`ShapedLine::paint()`) for actual glyph rendering. Cannot bypass the platform text pipeline.
3. **Single-threaded rendering**: Demo renders synchronously on main thread. Snapshot architecture can be deferred.
4. **Small file target**: Demo files under 1,000 lines. O(N) edit propagation is acceptable.

## Implementation

The demo implementation is organized into 3 phases, prioritized by user-visible impact:

### Phase 1: Make Text Visible (Rendering Foundation)

**Goal**: Readable text, visible line numbers, correct scroll clipping.

1. **Replace per-glyph paint_quad with GPUI ShapedLine::paint()**
   - Use `window.text_system().shape_line()` to shape text with styled runs
   - Paint shaped lines via `ShapedLine::paint(origin, line_height, ...)`
   - Remove custom `TextRenderer` glyph atlas pipeline (replaced by GPUI's platform text system)
   - Reference: [[2026-02-05-editor-demo-rendering-reference]] Section 2

2. **Adopt Zed's 3-phase Element pattern**
   - Replace `RequestLayoutState = ()` with `EditorRequestLayoutState` (font metrics, gutter dims)
   - Replace `PrepaintState = ()` with `EditorLayout` struct (line layouts, selection rects, cursor positions, hitboxes)
   - Move line shaping and position computation to `prepaint`
   - Move all painting to `paint` (consuming the layout struct)
   - Reference: [[2026-02-05-editor-demo-rendering-reference]] Section 1

3. **Wire gutter painting into EditorElement::paint()**
   - Shape line numbers as `ShapedLine` in prepaint
   - Paint in gutter region during paint phase
   - Compute gutter dimensions from font metrics
   - Reference: [[2026-02-05-editor-demo-rendering-reference]] Section 3

4. **Add content masking**
   - Wrap paint operations in `window.with_content_mask(bounds)` to clip during scroll
   - Reference: [[2026-02-05-editor-demo-rendering-reference]] Section 1

5. **Register hitboxes**
   - Insert editor, gutter, and text-area hitboxes in prepaint
   - Required for Phase 2 mouse interaction
   - Reference: [[2026-02-05-editor-demo-rendering-reference]] Section 1

### Phase 2: Make Input Work (Event Integration)

**Goal**: Type text, navigate with keyboard, click to position cursor, select text with mouse.

1. **Implement EntityInputHandler on EditorView**
   - Bridge GPUI's platform input to editor buffer
   - Wire `replace_text_in_range` to `EditorState::insert()`
   - Wire `replace_and_mark_text_in_range` for IME composition
   - Reference: [[2026-02-05-editor-demo-events-reference]] Section 1

2. **Connect PositionMap to layout data**
   - Use prepaint-computed line positions for pixel-to-buffer coordinate mapping
   - Enable click-to-position and drag-to-select
   - Reference: [[2026-02-05-editor-demo-events-reference]] Section 5

3. **Add click count detection**
   - Track click timing for double-click (word select) and triple-click (line select)
   - Reference: [[2026-02-05-editor-demo-events-reference]] Section 5

4. **Add transaction grouping to undo/redo**
   - Group edits within 300ms into a single transaction
   - Restore cursor position on undo/redo
   - Reference: [[2026-02-05-editor-demo-core-reference]] Section 4

### Phase 3: Display Map Completeness (Transform Pipeline)

**Goal**: Correct tab rendering, working folds, block placement for future live preview.

1. **Implement InlayMap pass-through**
   - Pure identity transform: input coordinates == output coordinates
   - Enables future inlay hints without pipeline changes
   - Reference: [[2026-02-05-editor-demo-displaymap-reference]] Section 1

2. **Implement TabMap pass-through**
   - Expand hard tabs to spaces using configurable tab_size
   - Column-aware expansion (tabs align to tab stops)
   - Reference: [[2026-02-05-editor-demo-displaymap-reference]] Section 1

3. **Wire DisplayMap::sync() to call all layers**
   - Currently only syncs WrapMap; must sync InlayMap, FoldMap, TabMap, BlockMap
   - Reference: [[2026-02-05-editor-demo-displaymap-reference]] Section 5

4. **Add BlockPlacement::Replace**
   - Required foundation for markdown live preview
   - Enables hiding source syntax and replacing with rendered content
   - Reference: [[2026-02-05-editor-demo-displaymap-reference]] Section 7

## Rationale

### Why GPUI text system over custom atlas?

Our custom GlyphAtlas + per-glyph paint_quad is architecturally disconnected from GPUI's render pipeline. GPUI's `ShapedLine::paint()` uses platform-native text rendering (CoreText/DirectWrite/FreeType), handles subpixel AA, ligatures, and styled runs automatically. Switching to GPUI's text system is the single highest-impact change -- it replaces colored rectangles with actual readable text.

### Why 3-phase Element over current flat approach?

Zed's 3-phase pattern (request_layout -> prepaint -> paint) separates concerns: sizing, positioning, and rendering. Our current approach crams everything into `Render::render()` and a flat `paint()`, making it impossible to register hitboxes before painting or to pass layout data between phases. The rich `EditorLayout` struct enables clean data flow.

### Why defer snapshot architecture?

Snapshots are essential for production (concurrent render + edit), but the demo renders synchronously on the main thread. Adding snapshots now would increase complexity without visible benefit. They should be added when async wrapping or background rendering is needed.

### Why defer multi-cursor and anchors?

Single-cursor offset-based editing works correctly for the demo. Anchor-based positioning (needed for multi-cursor and edit-stable cursors) requires substantial SumTree work (`slice`/`append`/`suffix`) and a fundamentally different cursor model. Better to validate the rendering and input pipeline first.

## Consequences

### Positive

- A working interactive demo validates the entire editor stack end-to-end
- GPUI text system adoption eliminates the custom atlas maintenance burden
- 3-phase Element pattern aligns with GPUI best practices and Zed's proven architecture
- Phase-based approach allows incremental validation (visible text -> input -> transforms)

### Negative

- Custom TextRenderer and GlyphAtlas code (~460 lines) will be replaced/removed
- Phase 1 changes are substantial (EditorElement rewrite from 253 lines to ~800+)
- Demo will still have O(N) edit propagation for large files (acceptable under 1,000 lines)
- No live preview rendering until Phase 3 `BlockPlacement::Replace` is implemented

### Future Work (Post-Demo)

- SumTree `slice()`/`append()`/`suffix()` for incremental edit propagation
- Snapshot architecture for concurrent render/edit
- Async WrapMap background wrapping
- Multi-cursor with anchor-based positioning
- Typed action dispatch system for configurable keybindings
- CreaseMap for language-server fold ranges
- CustomHighlights for search/selection rendering

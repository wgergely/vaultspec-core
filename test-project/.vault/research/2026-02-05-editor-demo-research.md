---
tags:
  - "#research"
  - "#editor-demo"
date: 2026-02-05
related:
  - "[[2026-02-04-editor-event-handling]]"
  - "[[2026-02-04-advanced-editor-synthesis]]"
  - "[[2026-02-04-displaymap-reference]]"
  - "[[2026-02-05-editor-demo-core-reference]]"
  - "[[2026-02-05-editor-demo-events-reference]]"
  - "[[2026-02-05-editor-demo-rendering-reference]]"
  - "[[2026-02-05-editor-demo-displaymap-reference]]"
---

# Editor Demo Research: Interactive Full-Featured Editor Stub

Research into the current state of the editor crate ecosystem and what is required to produce a full-featured interactive editor demo suitable for integration testing and feature validation. Reference implementation: Zed Editor.

## Findings

### Current Crate Architecture (pp-editor-*)

| Crate | Lines | Purpose | Completeness |
|-------|-------|---------|-------------|
| pp-editor-core | ~4,000 | Framework-agnostic core (Buffer, Cursor, DisplayMap, Markdown, Syntax) | ~90% |
| pp-editor-events | ~6,400 | GPUI event handling (mouse, keyboard, focus, IME, hit testing) | ~95% |
| pp-editor-main | ~3,850 | GPUI widget bindings (EditorModel, EditorView, TextRenderer) | ~80% |

**Total: ~14,250 lines across 3 editor crates.**

### Existing Demo Infrastructure

Two demo examples exist in `pp-editor-main`:

- `examples/demo.rs` — Full editor demo with styling
- `examples/minimal.rs` — Minimal 11-line editor example

Three event examples exist in `pp-editor-events`:

- `examples/basic_button.rs` — Mouse click handling
- `examples/tab_navigation.rs` — Tab order
- `examples/text_input.rs` — Text input handling

**Gap:** No unified, full-featured interactive demo that exercises all subsystems together.

### Zed Reference Architecture (Key Modules)

| Module | Description | PP Equivalent |
|--------|-------------|---------------|
| `editor.rs` (27K+ lines) | Main Editor entity, state, commands | `pp-editor-main/editor_model.rs` |
| `element.rs` (3K+ lines) | GPUI Element rendering pipeline | `pp-editor-main/editor_view.rs` + `editor_element.rs` |
| `display_map/` (6 layers) | Coordinate transformation pipeline | `pp-editor-core/display_map/` (5 layers) |
| `movement.rs` | Navigation logic | `pp-editor-core/operations.rs` (partial) |
| `selections_collection.rs` | Multi-selection management | `pp-editor-core/cursor.rs` + `selection` |
| `test/` | EditorTestContext, marked snapshots | Integration tests (partial) |

### Coordinate System Comparison

**Zed (6 layers):**

```
BufferPoint → InlayPoint → FoldPoint → TabPoint → WrapPoint → BlockPoint → DisplayPoint
```

**PP-Editor (5 layers):**

```
BufferPoint → InlayMap → FoldMap → TabMap → WrapMap → BlockMap → DisplayPoint
```

Architecture is aligned. PP-Editor already mirrors Zed's layered transform pipeline.

### Critical Gaps for Full-Featured Demo

1. **Live Preview Rendering** — Markdown block rendering pipeline is partially implemented
2. **GPUI Integration Tests** — Many disabled behind `#[cfg(feature = "todo_gpui_tests")]`
3. **Block Rendering Pipeline** — Images, tables, custom blocks are partial
4. **Unified Demo Binary** — No single demo exercising core + events + rendering together
5. **Movement Module** — No dedicated movement module (spread across operations.rs)
6. **Anchor-Based Positioning** — Zed uses anchors that survive edits; PP uses offset-based cursors

### Cross-Reference Audit Domains

Four audit domains identified for reference-auditor agents:

1. **Core Editor State** — Compare `Editor` entity pattern, state management, command dispatch
2. **Event Handling** — Compare input handling, IME, selection drag, keystroke matching
3. **Rendering Pipeline** — Compare element rendering, gutter, cursor painting, selection rects
4. **Display Map Pipeline** — Compare transform layers, coordinate systems, snapshot patterns

### Recommendations

- Spawn 4 reference-auditor agents for parallel cross-reference auditing
- Each agent produces a discrete `<Reference>` document for its domain
- Findings will feed into an ADR for the interactive demo architecture
- The demo should exercise: text editing, markdown preview, folding, syntax highlighting, mouse selection, keyboard navigation, scroll, and block rendering

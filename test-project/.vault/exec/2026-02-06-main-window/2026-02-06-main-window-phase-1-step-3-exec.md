---
tags:
  - "#exec"
  - "#uncategorized"
date: 2026-02-06
---
# Phase 1, Step 3: Implement Frameless Window Resizing

## Objective

Implement logic for resizing the frameless window using GPUI's `window.start_window_resize(edge)`, including defining resize areas and cursor feedback.

## Research Findings

From the Zed GPUI codebase (`ref/zed/crates/gpui/examples/window_shadow.rs`):

1. **API**: `window.start_window_resize(edge: ResizeEdge)` initiates resize operation
2. **ResizeEdge enum**: Top, TopRight, Right, BottomRight, Bottom, BottomLeft, Left, TopLeft
3. **Cursor Feedback**: Use `window.set_cursor_style(style, &hitbox)` with appropriate cursor for each edge
4. **Hitbox Pattern**: Use `canvas()` element to create hitboxes for proper cursor management

## Implementation

### 1. Resize Edge Detection

Created `detect_resize_edge()` function that:

- Checks corners first (8px zones at each corner)
- Then checks edges (8px zones along each side)
- Returns `None` for interior content area
- Uses pixel-based coordinate comparison

```rust
fn detect_resize_edge(pos: Point<Pixels>, resize_area: Pixels, size: Size<Pixels>) -> Option<ResizeEdge>
```

### 2. Cursor Style Mapping

Created `cursor_for_resize_edge()` helper:

- `ResizeUpDown` for Top/Bottom edges
- `ResizeLeftRight` for Left/Right edges
- `ResizeUpLeftDownRight` for TopLeft/BottomRight corners
- `ResizeUpRightDownLeft` for TopRight/BottomLeft corners

### 3. Layered Architecture

Implemented two-layer approach:

**Canvas Layer (Absolute)**:

- Creates full-window hitbox
- Tracks mouse position
- Updates cursor style based on edge detection
- Does not block mouse events

**Content Layer (Normal Flow)**:

- Contains title bar and content
- Handles mouse down events
- Distinguishes between resize edges and drag areas
- Initiates appropriate window operation

### 4. Event Flow

```
Mouse Down → Detect Position:
├─ In resize area (8px from edge)? → window.start_window_resize(edge)
├─ In title bar (top 32px)? → window.start_window_move()
└─ In content area? → No action
```

## Technical Details

- **Resize Area**: 8px from all edges (configurable via `resize_area` variable)
- **Title Bar**: 32px high drag zone at top
- **Layering**: Absolute canvas overlay + normal content flow
- **Event Handling**: Mouse down on content layer, cursor on canvas layer

## Testing

✅ **Compilation**: Code compiles without errors
✅ **Linting**: Passes `cargo clippy` with no warnings
✅ **Formatting**: Passes `cargo fmt`

## Code Quality

- **Safety**: No unsafe code
- **Idioms**: Follows GPUI canvas/hitbox pattern from official examples
- **Modularity**: Helper functions for edge detection and cursor mapping
- **Documentation**: Inline comments explain the two-layer architecture

## Files Modified

- `crates/pp-ui-mainwindow/src/main_window.rs`

## Next Steps

Phase 1, Step 4 will implement the `set_bounds` mechanism for programmatic window positioning, which requires:

- Platform-specific unsafe code for Windows (`SetWindowPos`) and macOS (`NSWindow::setFrame`)
- Unified trait or wrapper for cross-platform API
- Safety documentation for unsafe blocks

## Status

**COMPLETED** - Frameless window resizing successfully implemented with proper cursor feedback and edge detection.

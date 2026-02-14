---
feature: main-window
phase: 1-foundation
step: 2
date: 2026-02-06
status: completed
---

# Phase 1, Step 2: Implement Frameless Window Dragging

## Objective

Add functionality for dragging the frameless window using GPUI's `window.start_window_move()`, and implement custom drag handles.

## Research Findings

From the Zed GPUI codebase (`ref/zed/crates/gpui`):

1. **API**: `window.start_window_move()` is the correct API for initiating window dragging
2. **Pattern**: Mouse down handler triggers the drag operation
3. **Event Binding**: Use `.on_mouse_down(MouseButton::Left, |_event, window, _cx| { ... })`

**Reference**: `ref/zed/crates/gpui/examples/window_shadow.rs` lines 161-165

## Implementation

### 1. Custom Title Bar Drag Handle

Created a 32px height custom title bar area that serves as the drag handle:

```rust
div()
    .h(px(32.0))
    .w_full()
    .bg(rgb(0x3b4252))  // Slightly lighter than background
    .flex()
    .items_center()
    .px_3()
    .on_mouse_down(MouseButton::Left, |_event, window, _cx| {
        // Start window drag on left mouse button down
        window.start_window_move();
    })
    .child(/* title text */)
```

### 2. Updated Window Layout

- **Title Bar**: Fixed 32px height with drag functionality
- **Content Area**: Uses `.flex_1()` to fill remaining space
- **Visual Feedback**: User instructions displayed in content area

### 3. API Updates

Updated imports to match current GPUI API:

- `Application::new()` instead of `App::new()`
- `cx: &mut App` instead of `cx: &mut AppContext`
- `size(px(width), px(height))` for window dimensions
- `cx.new()` instead of `cx.new_view()` for entity creation

## Testing

✅ **Compilation**: Code compiles without errors
✅ **Linting**: Passes `cargo clippy` with no warnings
✅ **Formatting**: Passes `cargo fmt`

## Code Quality

- **Safety**: No unsafe code
- **Idioms**: Uses GPUI's native event system
- **Readability**: Clear comments and logical structure
- **Standards Compliance**: Follows Rust 2024 edition standards

## Files Modified

- `crates/pp-ui-mainwindow/src/main_window.rs`

## Next Steps

Phase 1, Step 3 will implement window resizing using `window.start_window_resize(edge)` with:

- Edge detection logic
- Resize areas (corners and edges)
- Cursor style feedback

## Status

**COMPLETED** - Frameless window dragging successfully implemented using GPUI's native API.

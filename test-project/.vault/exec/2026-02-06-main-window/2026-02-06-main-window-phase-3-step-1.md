---
feature: main-window
phase: 3-interaction
step: 1
date: 2026-02-07
status: completed
---

# Phase 3, Step 1: Active Snapping Integration

## Objective

Feed the proposed window position and size into `pp-core-snappoints::SnapEngine::snap_window` during active drag or resize events.

## Implementation

### 1. Fixed GPUI Entity Creation API

Replaced broken `current_app_cx.new_entity(...)` with correct `cx.new(|cx| { ... })` pattern per GPUI's `AppContext` trait:

```rust
cx.new(|cx: &mut Context<MainWindow>| {
    // ... entity setup
    MainWindow { ... }
})
```

### 2. Fixed Bounds Observation

Replaced direct private field access `window_ctx.bounds_observers.insert(...)` with the public `observe_window_bounds` API:

```rust
cx.observe_window_bounds(window, |this, window, cx| {
    this.on_bounds_changed(window, cx);
}).detach();
```

### 3. Type Conversion Bridge

Created conversion helpers between GPUI types and `pp-core-snappoints` types:

- `gpui_origin_to_snap_point(Point<Pixels>) -> snappoints::Point`
- `gpui_size_to_snap_size(Size<Pixels>) -> snappoints::Size`
- `snap_point_to_gpui_origin(snappoints::Point) -> Point<Pixels>`

### 4. Active Snap Calculation

In `on_bounds_changed`, when `snap_state.is_active`:

1. Get current window bounds from GPUI
2. Convert to snappoints types
3. Call `snap_engine.snap_window(pos, size)`
4. Convert result back to GPUI `Bounds<Pixels>`
5. Apply 1px jitter threshold to avoid micro-oscillation

### 5. Dynamic Screen Size

Replaced hardcoded 1920x1080 with actual display query:

```rust
fn query_screen_area(app_cx: &App) -> ScreenRect {
    if let Some(display) = app_cx.primary_display() {
        let bounds = display.bounds();
        ScreenRect::new(...)
    } else {
        // Fallback to 1920x1080
    }
}
```

## Files Modified

- `crates/pp-ui-mainwindow/src/main_window.rs`: Complete rewrite of entity creation, bounds observation, and snap integration

## Status

**COMPLETED** - Active snapping integration fully wired up.

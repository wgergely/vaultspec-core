---
feature: main-window
phase: 3-interaction
step: 2
date: 2026-02-07
status: completed
---

# Phase 3, Step 2: Apply Snapped Bounds

## Objective

Apply the calculated snapped position and size from `SnapEngine` to the GPUI window using the `set_bounds` mechanism from Phase 1.

## Implementation

### 1. Windows `set_bounds` (Already Functional)

The Windows implementation via `SetWindowPos` was already functional from Phase 1:

- Gets HWND via `HasWindowHandle` trait
- Converts logical pixels to physical
- Calls `SetWindowPos` with `SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED`

### 2. macOS `set_bounds` (Completed from Skeleton)

Implemented the previously-skeleton macOS `set_bounds`:

```rust
pub(super) fn set_bounds(window: &Window, bounds: Bounds<Pixels>) -> Result<(), String> {
    let ns_window = get_nswindow_from_window(window)?;

    // Get screen height for coordinate conversion
    let screen_height: f64 = unsafe {
        let main_screen: id = msg_send![class!(NSScreen), mainScreen];
        let frame: NSRect = msg_send![main_screen, frame];
        frame.size.height
    };

    // Convert top-left origin (GPUI) → bottom-left origin (macOS)
    let y_flipped = screen_height - y - height;

    unsafe { ns_window.setFrame_display_(frame, YES); }
    Ok(())
}
```

### 3. Snapped Bounds Application in Bounds Observer

The `on_bounds_changed` method applies snapped bounds:

```rust
if origin_delta_x > threshold || origin_delta_y > threshold {
    self.snap_state.target_bounds = Some(snapped);
    if let Err(e) = crate::platform::set_window_bounds(window, snapped) {
        tracing::warn!("Failed to apply snapped bounds: {e}");
    }
}
```

### Safety Documentation

- macOS: All unsafe blocks document invariants (valid NSWindow, main thread, coordinate system)
- Windows: Existing safety docs from Phase 1 preserved
- Error handling: Failures logged via `tracing::warn!`, never panics

## Files Modified

- `crates/pp-ui-mainwindow/src/main_window.rs`: `on_bounds_changed` applies snapped bounds
- `crates/pp-ui-mainwindow/src/platform/macos.rs`: Complete `set_bounds` implementation
- `crates/pp-ui-mainwindow/src/platform.rs`: `#[allow(dead_code)]` on unused `set_window_position`

## Status

**COMPLETED** - Snapped bounds are applied via platform-specific `set_bounds` on both Windows and macOS.

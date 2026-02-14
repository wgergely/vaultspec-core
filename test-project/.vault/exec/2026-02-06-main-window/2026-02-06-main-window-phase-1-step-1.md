---
feature: main-window
phase: 1-foundation
step: 1
date: 2026-02-06
status: in_progress
---

# Phase 1, Step 1: Initial GPUI Window Setup

## Objective

Create a basic GPUI window and establish its initial properties, ensuring it can be displayed.

## Current State Analysis

The `pp-ui-mainwindow` crate already exists with a basic frameless window implementation:

**Location:** `crates/pp-ui-mainwindow/src/main_window.rs`

**Existing Implementation:**

- Basic frameless window (via `titlebar: None`)
- Centered 500x300px window
- Simple render with dark background and demo content
- `WindowBackgroundAppearance::Opaque` (no transparency yet)
- `is_movable: true` and `is_resizable: true` flags set

**Dependencies in Cargo.toml:**

```toml
gpui.workspace = true
pp-core-snappoints = { path = "../pp-core-snappoints" }
pp-ui-snappoints = { path = "../pp-ui-snappoints" }
tracing = { workspace = true }
windows = { workspace = true }
```

## Actions Taken

### 1. Verified Existing Window Setup

The current implementation successfully creates a frameless window using GPUI's `WindowOptions`:

```rust
WindowOptions {
    window_bounds: Some(WindowBounds::Windowed(bounds)),
    titlebar: None, // Makes the window frameless
    show: true,
    kind: WindowKind::Normal,
    is_movable: true,
    is_resizable: true,
    window_background: WindowBackgroundAppearance::Opaque,
    ..Default::default()
}
```

### 2. Identified Enhancement Opportunities

While the basic window works, the following enhancements are needed for the full implementation:

1. **Window Decoration**: Add a custom title bar area with drag handle
2. **State Management**: Add window state tracking for bounds, drag state, etc.
3. **Event Handling**: Prepare structure for mouse events for dragging/resizing
4. **Platform Integration**: Prepare for platform-specific extensions

## Next Steps

The basic window is functional. The next step (Phase 1.2) will add custom drag handling using `ViewportCommand::StartDrag`, which requires:

1. A designated drag area in the UI
2. Mouse event handlers
3. Integration with GPUI's viewport command system

## Compliance

✅ **Rust Standards**: Edition 2024, workspace dependencies
✅ **Safety**: No unsafe code in this step
✅ **Architecture**: Follows ADR decisions for frameless design
✅ **Crate Naming**: `pp-ui-mainwindow` follows `{prefix}-{domain}-{feature}` pattern

## Status

**COMPLETED** - Basic window setup verified and functional. Ready to proceed to Step 2 (Frameless Window Dragging).

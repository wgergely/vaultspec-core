---
feature: gpui-snapping-architecture
date: 2026-02-06
related: [[2026-02-06-displaymap-architecture-design.md]]
---

# GPUI Window Snapping Architecture Research

This document outlines the research findings for implementing a custom window snapping grid system in GPUI, focusing on window event interception, application of the `SnapGrid` logic, and best practices for visual feedback during drag operations.

## 1. Intercepting Window Movement and Resize Events in GPUI

GPUI provides mechanisms to detect when a window's bounds change due to user interaction (move or resize).

* **`PlatformWindow::on_moved` and `PlatformWindow::on_resize` callbacks:** The `PlatformWindow` trait, implemented by platform-specific window backends (e.g., `WindowsWindow`, `X11Window`, `WaylandWindow`), exposes `on_moved` and `on_resize` methods. These methods accept closures that are invoked when the native window is moved or resized.
* **`Window::bounds_changed`:** Within the `gpui::Window` struct (found in `ref/zed/crates/gpui/src/window.rs`), the callbacks from `on_moved` and `on_resize` ultimately trigger a call to `window.bounds_changed(cx)`.
* **`Window::bounds_observers`:** The `bounds_changed` method then notifies subscribers of the `bounds_observers` `SubscriberSet`. This provides a GPUI-idiomatic way to register a callback that will be executed whenever the window's position or size changes.

**Conclusion for Event Interception:** We can subscribe to `Window::bounds_observers` to be notified of window movement and resize events.

## 2. Applying 'SnapGrid' Logic to Modify GPUI Window Bounds

The `crates/pp-core-snappoints` crate provides the core logic for the snapping grid.

* **`pp-core-snappoints::GridConfig`:** Defines grid properties such as columns, rows, and snap threshold.
* **`pp-core-snappoints::SnapGrid`:** Instantiated with a `ScreenRect` (representing the area for snapping, e.g., monitor bounds) and a `GridConfig`. It provides methods like `nearest_point_xy` to find the closest grid point and `span_rect` to calculate the bounds for multiple grid cells.
* **`pp-core-snappoints::SnapEngine`:** Takes a `SnapGrid` and `SnapThresholds`. Its `snap_window(pos: Point, size: Size) -> Point` method is crucial. It calculates a snapped position for the top-left corner of a window and clamps it within the grid's defined area. This method will be used to determine the target position for a window after a drag or resize operation.

**Current Challenge: Setting GPUI Window Bounds Programmatically**

* **Retrieving current bounds:** The `Window::bounds() -> Bounds<Pixels>` method successfully returns the current window's position and size. This output can be directly fed into `SnapEngine::snap_window`.
* **Programmatic setting of bounds:**
  * **GPUI Abstraction (`Window` struct):** The `gpui::Window` struct itself offers `pub fn resize(&mut self, size: Size<Pixels>)`, but this only sets the content size and explicitly uses `SWP_NOMOVE` on Windows, meaning it doesn't change the window's position. There is no public or crate-private `set_position` or `set_bounds` method available directly on the `Window` struct.
  * **Platform-specific implementations (`PlatformWindow` trait):**
    * **Linux (X11 & Wayland):** Research shows that platform-specific implementations (e.g., `X11Window`, `WaylandWindow`) *do* provide methods like `set_bounds(bounds: Bounds<i32>)` or `set_geometry(x: i32, y: i32, width: i32, height: i32)`. This indicates that the functionality exists at the platform level and is exposed for Linux.
    * **Windows:** The `WindowsWindow` implementation of `PlatformWindow` for Windows relies on the Win32 API function `SetWindowPos`. While `SetWindowPos` is capable of setting both position and size simultaneously, GPUI's current `resize` implementation explicitly uses the `SWP_NOMOVE` flag, preventing position changes. A generic `set_bounds` method is not exposed at the `PlatformWindow` trait level for Windows.

**Proposed Solution for Windows (and Generalization):**

To achieve programmatic snapping that can adjust both position and size on Windows, GPUI's `PlatformWindow` trait (or its Windows-specific implementation) needs to be extended. A new method, perhaps `set_bounds(&mut self, bounds: Bounds<Pixels>)`, should be introduced. This method would internally utilize `SetWindowPos` on Windows (without `SWP_NOMOVE`) and call the existing `set_bounds`/`set_geometry` methods on Linux. This would provide a unified API for setting window bounds across platforms.

## 3. Best Practices for Visual Feedback (Overlaying the Grid) During Drag

Visual feedback during a drag or resize operation is crucial for a good user experience. This involves dynamically drawing a representation of the snapping grid.

* **GPUI Drawing Primitives:** The `gpui::Window` struct (specifically through its `paint_quad`, `paint_path`, etc., methods) provides access to GPUI's rendering capabilities. These primitives can be used to draw lines, rectangles, and other shapes directly onto the window's canvas.
* **Custom GPUI Element for Overlay:** The best practice would be to create a custom GPUI `Element` (or `View`) that is responsible for rendering the snapping grid. This element would:
  * Be positioned as an overlay on top of the main window content.
  * Dynamically update its drawing based on the current mouse position (during drag) and the calculated `SnapGrid` target bounds.
  * Only be visible when a window is actively being dragged or resized.
  * Use the `Window::paint_quad` or similar methods to render the grid lines and potential target snap areas.
* **Dynamic Visibility:** The visibility of the grid overlay element would be controlled by a state variable within the main window's view or controller, toggled when a drag/resize operation starts and ends.

## Conclusion and Next Steps

Implementing a custom window snapping grid in GPUI is feasible. The necessary components for event interception and snapping logic are present. The primary architectural hurdle is the current lack of a high-level, cross-platform GPUI API to programmatically set an existing window's position and size simultaneously.

**Next Steps:**

1. **Develop a unified `set_bounds` mechanism:** Implement a cross-platform method within GPUI that allows setting the full `Bounds` of an existing window. This will likely involve extending the `PlatformWindow` trait and its platform-specific implementations.
2. **Integrate SnapEngine with GPUI window events:** Hook the `SnapEngine` into the `Window::bounds_observers` to calculate snapped positions and then apply these new bounds using the `set_bounds` mechanism.
3. **Implement visual grid overlay:** Create a custom GPUI `Element` to render the snapping grid as an overlay during drag operations, utilizing `Window::paint_quad` for drawing.
4. **Monitor Information:** Utilize `Platform::displays()` and `PlatformDisplay::bounds()` to get the necessary `ScreenRect` for initializing `SnapGrid`.

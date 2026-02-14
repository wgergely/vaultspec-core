---
feature: rust-window-positioning
date: 2026-02-06
related: []
---

# Rust Window Positioning Research

## Objective

Research how Zed editor and other mature Rust GUI apps (like Tauri/Wry or Druid) handle programmatic window positioning (moving) and resizing on Windows and macOS. Specifically, look for patterns in 'ref/zed' or open-source references for 'SetWindowPos' (Windows) and 'setFrame' (macOS) usage within a platform-abstracted context. Determine if a 'patch' to GPUI is the standard way or if there's an existing 'WindowContext' API we missed.

## Findings

The research focused primarily on Zed's GPUI framework, as it is the foundation for our project.

### GPUI Window Management (ref/zed)

- **Platform-Specific Implementations**: GPUI handles window management by encapsulating platform-specific API calls within its `platform` modules.
  - **Windows**: For Windows, the `gpui/src/platform/windows/window.rs` and `gpui/src/platform/windows/events.rs` files show heavy reliance on the Win32 API function `SetWindowPos`.
    - `SetWindowPos` is used for a variety of operations: initial window placement, toggling fullscreen mode, handling DPI changes, and general resizing.
    - Specific flags like `SWP_NOMOVE`, `SWP_NOSIZE`, `SWP_NOZORDER`, `SWP_NOACTIVATE`, and `SWP_FRAMECHANGED` are used to control the exact behavior of the window positioning and sizing operations.
    - The `calculate_window_rect` and `SetWindowPlacement` functions are also involved in managing window state and restoring positions.
  - **macOS**: For macOS, the `gpui/src/platform/mac/window.rs` file utilizes Cocoa APIs, primarily `NSWindow` methods like `setFrame:display:animate:` and `setContentSize:`.
    - `setFrameTopLeftPoint_` is used during window initialization for accurate placement, especially when dealing with multiple displays.
    - `setContentSize_` is directly used for resizing the window's content area.
    - Window buttons and other UI elements' positions are also managed through these frame manipulation functions.

- **`PlatformWindow` Trait**: GPUI provides a `PlatformWindow` trait which abstracts common window operations. However, the existing trait primarily exposes a `resize` method that only affects size, and other positioning aspects (like initial placement or state changes) are handled internally or through specific, higher-level GPUI constructs.

- **Lack of Generic Positioning API**: There is no generic, high-level `WindowContext` API within GPUI that allows for arbitrary programmatic window positioning (moving) or sizing (beyond simple resizing) after the window has been created. The existing abstraction focuses on providing the necessary primitives for the framework itself to manage the window lifecycle and state.

## Conclusion & Recommendation

**Conclusion**: Zed's GPUI framework directly interacts with underlying operating system APIs for detailed window positioning and resizing. While GPUI offers a `PlatformWindow` trait for some common operations, it does not currently provide a high-level, cross-platform API for arbitrary programmatic window moving or precise sizing post-creation.

**Recommendation**: To achieve programmatic window positioning and resizing for custom layouts (e.g., for features like grid snapping or complex window arrangements), the most appropriate approach would be to **extend the `PlatformWindow` trait** within GPUI. This extension would involve adding new methods such as `set_position(&self, point: Point<Pixels>)` and/or `set_bounds(&self, bounds: Rect<Pixels>)`. These new methods would then require platform-specific implementations for Windows (using `SetWindowPos`) and macOS (using `setFrame:` or similar `NSWindow` methods). This approach maintains GPUI's abstraction layer while providing the necessary control for advanced window management features.

Further investigation into how other Rust GUI frameworks (Tauri/Wry, Druid) expose similar low-level window controls could provide additional insights for the API design of these extensions, though the direct integration with GPUI suggests focusing on extending its existing `PlatformWindow` trait is the most direct path.

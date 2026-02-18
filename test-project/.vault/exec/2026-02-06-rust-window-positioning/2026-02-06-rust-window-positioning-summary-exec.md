---
tags:
  - "#exec"
  - "#uncategorized"
date: 2026-02-18
---
## 2026-02-06-rust-window-positioning-research - Summary

The research into programmatic window positioning and resizing in Rust GUI applications, with a focus on Zed editor's GPUI framework, has been completed. The findings are documented in `.docs/research/2026-02-06-rust-window-positioning-research.md`.

**Key Findings:**

* **Platform-Specific Implementation:** Zed's GPUI heavily relies on direct platform-specific API calls for window management.
  * On **Windows**, `SetWindowPos` is extensively used for initial placement, resizing, DPI changes, and fullscreen toggling, with various `SWP_*` flags controlling behavior. `SetWindowPlacement` is also used for state restoration.
  * On **macOS**, Cocoa APIs like `NSWindow::setFrame:display:animate:` and `setContentSize:` are utilized for frame manipulation, initial positioning via `setFrameTopLeftPoint_`, and content area resizing.
* **`PlatformWindow` Trait:** GPUI provides a `PlatformWindow` trait for abstraction, but it primarily offers a `resize` method. Other positioning aspects are handled internally or through higher-level GPUI constructs.
* **No High-Level API for Arbitrary Positioning:** There is no generic, high-level `WindowContext` API within GPUI for arbitrary programmatic window moving or precise sizing *after* creation.

**Recommendation:**

To enable programmatic window positioning and resizing for custom layouts (e.g., grid snapping), it is recommended to **extend the `PlatformWindow` trait** with new methods like `set_position` or `set_bounds`. These methods would then require specific implementations for each platform (Windows and macOS), leveraging the underlying OS APIs (`SetWindowPos` on Windows, `setFrame:` on macOS). This approach would maintain GPUI's abstraction while providing the necessary control for advanced window management features.

---
tags:
  - "#adr"
  - "#uncategorized"
date: 2026-02-06
related:
  - "[[2026-02-06-legacy-mainwindow-audit.md]]"
  - "[[2026-02-06-advanced-window-effects-research.md]]"
  - "[[2026-02-06-gpui-snapping-architecture-research.md]]"
  - "[[2026-02-06-external-rust-windowing-references.md]]"
---
# Main Window Architecture: Frameless Design, Advanced Effects, and Snapping Grid Integration

## Context

The main application window is a critical component, requiring a modern, customizable aesthetic that aligns with the project's vision of an Obsidian/ZED-like editor. This necessitates a frameless design, support for advanced visual effects (such as transparency, blur, and platform-native acrylic/vibrancy), and a precise, user-friendly window snapping grid system for enhanced productivity. The project already has an established `pp-core-snappoints` crate providing core snapping logic, and GPUI serves as the chosen UI framework.

## Decisions

### 1. Adopt a Frameless Window Architecture

**Rationale:**

* Provides complete control over the window's visual presentation, including the title bar, borders, and general window chrome, enabling a custom, modern UI consistent with the project's design language.
* Facilitates the implementation of custom drag handles and resize areas that are integral to the desired user experience.

**Implications:**

* Requires the manual implementation of standard window behaviors like dragging and resizing, although GPUI's abstractions and the underlying `winit` crate simplify much of this.
* On Windows, it may be necessary to explicitly handle the `WM_NCHITTEST` message to ensure compatibility with native snap layout functionality (e.g., the snap assist menu that appears when hovering over the maximize button), similar to approaches seen in projects like `tauri-plugin-decorum`.
* GPUI's `ViewportCommand::StartDrag` and `ViewportCommand::BeginResize` will be used to delegate the actual window movement and resizing operations to the operating system, ensuring native performance and feel.

### 2. Implement Platform-Specific `unsafe` Extensions for Window Positioning and Advanced Effects

**Rationale:**

* Achieving authentic platform-native Acrylic/Vibrancy effects, as well as precise programmatic control over window positioning (which is crucial for snapping), often necessitates direct interaction with low-level operating system APIs.
* While GPUI offers powerful abstractions, it may not expose all the granular controls required for these advanced, platform-specific visual and behavioral features.
* The established practice within the Rust ecosystem, evidenced by crates like `tauri-apps/window-vibrancy`, demonstrates that using `unsafe` blocks for these specific integrations is a necessary and acceptable approach when carefully managed.

**Details & Implications:**

* **Window Positioning:**
  * **Windows:** Utilize the `SetWindowPos` function via the `windows-rs` crate. This will require obtaining the native `HWND` (window handle) from the GPUI `Window` instance. Crucially, the `SWP_NOMOVE` flag must be avoided when attempting to programmatically set the window's position.
  * **macOS:** Interact with the `NSWindow` object and its `setFrame:display:` method, which will involve Objective-C interop through crates like `cocoa`.
  * A unified `set_bounds` mechanism will be developed, either by extending GPUI's `PlatformWindow` trait or by creating a custom wrapper, to abstract these platform-specific API calls.
* **Acrylic/Vibrancy Effects:**
  * **Windows:** Implementations will leverage Desktop Window Manager (DWM) APIs such as `DwmSetWindowAttribute` and `DwmEnableBlurBehindWindow` for blur effects, and potentially `SetWindowCompositionAttribute` for Acrylic.
  * **macOS:** The `NSVisualEffectView` will be utilized. This typically involves creating an `NSVisualEffectView` and adding it as a subview to the `NSWindow`'s content view, ensuring proper layering.
  * Conditional compilation (`#[cfg(target_os = "windows")]`, `#[cfg(target_os = "macos")]`) will be extensively used to manage these platform-specific code paths.
* **Safety:** All `unsafe` blocks will be rigorously encapsulated within dedicated, platform-specific modules. They will be accompanied by thorough documentation outlining their safety invariants and justifying their necessity, adhering strictly to Rust's guidelines for `unsafe` code.

### 3. Integrate the `pp-core-snappoints` Logic for the Snapping Grid

**Rationale:**

* The `pp-core-snappoints` crate is an existing, robust component that provides sophisticated and configurable logic for a snapping grid, including `SnapGrid` and `SnapEngine`.
* Reusing this well-tested and familiar component will prevent redundant development of complex geometry and snapping algorithms, saving development time and ensuring consistency.

**Implications:**

* **Event Handling:** The snapping logic will subscribe to `gpui::Window::bounds_observers` to receive notifications whenever the window is moved or resized by the user.
* **Snapping Calculation:** During an active window drag or resize operation, the proposed window position and size will be fed into `pp-core-snappoints::SnapEngine::snap_window`. This method will compute the optimal snapped target position and size based on the configured grid.
* **Applying Snapped Bounds:** The calculated snapped position and size will then be applied to the GPUI window using the platform-specific `set_bounds` mechanism defined in Decision 2.
* **Visual Feedback:** A custom GPUI `Element` will be developed to render a dynamic visual representation of the snapping grid. This element will function as an overlay, its visibility toggled to appear only during window drag or resize operations, utilizing GPUI's drawing primitives (e.g., `Window::paint_quad`) to provide real-time feedback to the user.

## Status

Proposed

## Consequences

**Benefits:**

* **Highly Customizable UI:** Full control over the main window's appearance and behavior, enabling a distinct and modern user interface.
* **Enhanced User Experience:** Precise window snapping grid improves usability and organization, aligning with editor productivity goals.
* **Code Reusability:** Leverages the existing and validated `pp-core-snappoints` logic, reducing development effort and potential bugs.
* **Consistent Aesthetics:** Achieves platform-native visual effects like Acrylic/Vibrancy, providing a polished and integrated look within each operating system.

**Drawbacks:**

* **Increased Complexity:** Introduction of platform-specific `unsafe` code and direct operating system API calls adds to the project's complexity and maintenance burden.
* **Platform Inconsistencies:** There is a risk of subtle behavioral or visual inconsistencies across platforms if the native integrations are not meticulously developed and tested.
* **Performance Considerations:** Advanced visual effects, particularly blur and transparency, can be computationally intensive and may impact application performance or battery life on less powerful hardware. Careful optimization will be required.
* **GPUI Integration Challenges:** Requires careful and potentially low-level integration with GPUI's rendering pipeline and event loop to ensure smooth operation of custom window behaviors and effects.

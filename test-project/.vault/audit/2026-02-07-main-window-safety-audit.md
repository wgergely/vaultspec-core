---
feature: main-window-safety-audit
date: 2026-02-07
related:
  - [[2026-02-06-main-window-architecture.md]]
---

# Rust Code Safety Audit: `crates/pp-ui-mainwindow` (Platform Modules)

## Overview

This audit focuses on the `unsafe` blocks, FFI interactions, and memory safety within the platform-specific modules `crates/pp-ui-mainwindow/src/platform/windows.rs` and `crates/pp-ui-mainwindow/src/platform/macos.rs`. The primary goal is to ensure adherence to the "No-Crash" policy, memory safety, and proper documentation of safety invariants as per project standards.

## Audit Findings

### `crates/pp-ui-mainwindow/src/platform/windows.rs`

This module manages Windows-specific window bounds and visual effects.

#### `set_bounds` function

* **`unsafe` Block Context**: The `unsafe` block encapsulates the call to the Win32 API function `SetWindowPos`.
* **Documented Safety Invariants**: Explicitly documented as:
    1. **Valid HWND**: The window handle must be valid and owned by this process.
    2. **Coordinate Validity**: Coordinates must be within valid screen bounds.
    3. **Thread Safety**: Must be called from the main/UI thread.
* **Verification of Invariants**:
  * **Valid HWND**: The `HWND` is obtained via `get_hwnd_from_window`, which relies on `gpui::Window` providing a valid `RawWindowHandle::Win32`. This assumption is reasonable within the GPUI framework.
  * **Coordinate Validity**: Coordinates are derived from `gpui::Bounds<Pixels>`. A `TODO` exists for handling the actual scale factor from the window display; currently, a fixed `1.0` is used. While conversion from `f32` to `i32` is mathematically safe, the fixed scale factor could lead to visual discrepancies on high-DPI displays or multi-monitor setups, though not directly a memory safety issue.
  * **Thread Safety**: Documented as guaranteed by the GPUI event loop.
* **FFI and Memory Safety**: The `HWND` handle conversion in `get_hwnd_from_window` from `NonNull<c_void>` to `*mut core::ffi::c_void` is standard and appropriate for FFI. `SetWindowPos` does not involve complex memory ownership transfers.
* **Error Handling**: The `windows::core::Result` from `SetWindowPos` is checked, and an error message is returned on failure, which is good practice.

#### `get_hwnd_from_window` function

* **`unsafe` Block Context**: No explicit `unsafe` block, but critical for FFI safety.
* **Documented Safety Invariants**: States reliance on `Window` representing a valid, existing native window and platform specificity.
* **Verification of Invariants**: Relies on `gpui::Window` implementing `HasWindowHandle` and correctly providing a `RawWindowHandle::Win32`. This is a reasonable architectural assumption.

#### `enable_acrylic_effect` function

* **`unsafe` Block Context**: Encompasses dynamic loading of `SetWindowCompositionAttribute` from `user32.dll` and its invocation.
* **Documented Safety Invariants**:
  * `hwnd` is assumed to be a valid window handle.
  * `SetWindowCompositionAttribute` is dynamically loaded, and its existence/signature are assumed based on undocumented API knowledge.
  * FFI structs (`ACCENT_STATE`, `ACCENT_POLICY`, etc.) are `#[repr(C)]` and mirror C++ definitions.
* **Verification of Invariants**:
  * **`hwnd` validity**: Relies on the caller providing a valid `HWND`.
  * **Dynamic Loading/Undocumented API**: This is the most significant safety concern. `std::mem::transmute` is used to cast the dynamically loaded function pointer. This is safe only if the undocumented API's signature *exactly* matches `SetWindowCompositionAttributeFn`. Changes in future Windows updates could lead to undefined behavior. The documentation acknowledges this risk.
  * **`#[repr(C)]` Structs**: Correctly used to ensure C-compatible memory layout for FFI calls.
  * **Pointer Casts**: `&mut accent_policy as *mut _ as *mut core::ffi::c_void` is a correct way to pass a struct by reference to a C API expecting a void pointer.
* **Error Handling**: Robust error handling for `GetModuleHandleA`, `GetProcAddress`, and the `SetWindowCompositionAttribute` call itself.

### `crates/pp-ui-mainwindow/src/platform/macos.rs`

This module manages macOS-specific window bounds and visual effects.

#### `get_nswindow_from_window` function

* **`unsafe` Block Context**: No explicit `unsafe` block, but foundational for FFI.
* **Documented Safety Invariants**: Implicitly, that `gpui::Window` provides a valid `RawWindowHandle::AppKit`.
* **Verification of Invariants**: Correctly extracts `handle.ns_window` from `RawWindowHandle::AppKit` and casts it to `id`. Handles cases where the handle is not AppKit or retrieval fails.

#### `enable_vibrancy_effect` function

* **`unsafe` Block Context**: Large `unsafe` block making multiple Objective-C runtime calls via `msg_send!`.
* **Documented Safety Invariants**:
    1. `window` must be a valid GPUI Window.
    2. Must be called on the main thread.
    3. The `NSWindow` pointer derived from `window` must be valid.
* **Verification of Invariants**:
  * **Valid GPUI Window / NSWindow**: Relies on `get_nswindow_from_window` providing a valid `id`. Error handling logs a warning and returns on failure.
  * **Main Thread**: Documented as guaranteed by GPUI. This is crucial for Cocoa API calls.
  * **`msg_send!`**: The use of `msg_send!` is inherent to Objective-C FFI. Selectors (method names) and argument types (`id`, `NSRect`, `i64`, `NSAutoresizingMaskOptions`) appear to be correctly matched to standard Cocoa APIs. `nil` checks are used where appropriate (e.g., for `contentView`).
  * **Object Lifecycle**: Relies on Cocoa's ARC for `NSVisualEffectView` lifetime management once it's added as a subview.

#### `set_bounds` function

* **`unsafe` Block Context**: The `unsafe` block contains calls to `NSScreen::mainScreen()` (via `msg_send!`) and `ns_window.setFrame_display_`.
* **Documented Safety Invariants**:
    1. Valid `NSWindow` pointer.
    2. Coordinate system conversion (macOS uses bottom-left origin).
    3. Main thread execution.
    4. Memory management (NSWindow owned by app, not freed here).
* **Verification of Invariants**:
  * **Valid NSWindow**: Relies on `get_nswindow_from_window`.
  * **Coordinate System**: Correctly handles the Y-axis inversion required for macOS, using `screen_height` from `NSScreen::mainScreen()`.
  * **Main Thread**: Explicitly documented as guaranteed by GPUI.
  * **Memory Management**: Explicitly notes that `NSWindow` ownership is with the application, not managed by this function.

## Recommendations

1. **Address `windows.rs` Scale Factor `TODO`**: The `TODO` regarding the actual scale factor in `set_bounds` in `windows.rs` should be prioritized. Incorrect scaling can lead to visual layout issues on different DPI settings, potentially degrading the user experience. This impacts the "Coordinate Validity" invariant.
2. **Runtime Main Thread Assertion (Debug Builds)**: While GPUI guarantees main thread execution, adding a debug-only runtime assertion (if an appropriate API exists in `gpui` or the platform) at the entry points of `enable_vibrancy_effect` (macOS) and `set_bounds` (both platforms) would help catch accidental thread-safety violations during development. This would reinforce the "Thread Safety" invariant.
3. **Undocumented API Stability (windows.rs)**: Reiterate the inherent instability risk of relying on the undocumented `SetWindowCompositionAttribute` in `windows.rs`. For a production-grade application, consider investigating officially supported alternatives for achieving similar effects in newer Windows SDKs. If no suitable official alternative exists, the current documentation correctly highlights the risk.
4. **Error Propagation Clarity**: Both platform modules handle errors gracefully, either by propagating `Result<_, String>` or logging warnings. This is consistent and acceptable.

## Conclusion

The `unsafe` blocks in `crates/pp-ui-mainwindow/src/platform/windows.rs` and `crates/pp-ui-mainwindow/src/platform/macos.rs` are generally well-documented with explicit safety invariants. The FFI interactions largely follow standard patterns for interacting with Windows Win32 API and macOS Cocoa APIs. The primary areas for improvement involve addressing the Windows scale factor `TODO` and being acutely aware of the risks associated with undocumented APIs, with a suggestion for debug-time main thread assertions. Overall, the code demonstrates a good understanding of platform-specific FFI and memory safety considerations.

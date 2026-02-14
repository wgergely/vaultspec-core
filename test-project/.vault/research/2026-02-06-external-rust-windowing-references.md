# Research: External Rust Windowing References

- **Date:** 2026-02-06
- **Topic:** High-quality implementations of window positioning, vibrancy, and custom dragging/snapping in Rust.
- **Related:** [[2026-02-06-incremental-layout-engine-design-adr]]

## 1. Programmatic Window Positioning and Resizing

Reliable window positioning requires interacting with platform-specific APIs. Reputable projects like `tauri-apps/tao` (a `winit` fork) and `druid` provide robust abstractions.

### Windows (`SetWindowPos`)

In `tao`, window positioning is handled by calling the Windows `SetWindowPos` function.

- **Project:** [tauri-apps/tao](https://github.com/tauri-apps/tao)
- **File:** `src/platform_impl/windows/window.rs`
- **Pattern:**

  ```rust
  // Simplified logic from tao
  unsafe {
      SetWindowPos(
          hwnd,
          HWND_TOP,
          x, y,
          width, height,
          SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED,
      );
  }
  ```

- **Key Insight:** `tao` handles high-DPI scaling automatically by converting logical coordinates to physical pixels before calling `SetWindowPos`.

### macOS (`setFrame:display:`)

On macOS, positioning is done via `NSWindow`.

- **Project:** [tauri-apps/tao](https://github.com/tauri-apps/tao)
- **File:** `src/platform_impl/macos/window.rs`
- **Pattern:** Uses `setFrame:display:` to update the window's geometry.

  ```objectivec
  // Conceptual objective-c called via objc runtime in Rust
  [window setFrame:NSMakeRect(x, y, width, height) display:YES];
  ```

---

## 2. Acrylic, Vibrancy, and Mica Effects

The `window-vibrancy` crate is the industry standard for applying modern transparency effects in Rust.

- **Project:** [tauri-apps/window-vibrancy](https://github.com/tauri-apps/window-vibrancy)
- **Implementation Files:**
  - `src/windows.rs`: [View File](https://github.com/tauri-apps/window-vibrancy/blob/main/src/windows.rs)
  - `src/macos.rs`: [View File](https://github.com/tauri-apps/window-vibrancy/blob/main/src/macos.rs)

### Windows Acrylic/Mica

- **Acrylic (Win 10 1809+):** Uses the undocumented `SetWindowCompositionAttribute` API.
- **Mica (Win 11):** Uses the official `DwmSetWindowAttribute` with `DWMWA_SYSTEMBACKDROP_TYPE` or `DWMWA_MICA_EFFECT`.

### macOS Vibrancy

- Uses `NSVisualEffectView` added as a subview to the window's content view.
- Supports materials like `UnderWindowBackground`, `Menu`, `Sidebar`, etc.

---

## 3. Custom Window Dragging and Snapping

### Custom Dragging Implementation

When using frameless windows, you must manually initiate dragging.

- **Windows Pattern:**
  - Call `ReleaseCapture()` followed by `SendMessageW(hwnd, WM_NCLBUTTONDOWN, HTCAPTION, 0)`.
  - This hands over the drag operation to the OS.
- **macOS Pattern:**
  - Call `performWindowDragWithEvent:` on the `NSWindow`.

### Windows Snap Layouts (Frameless Windows)

Custom titlebars often break the "Snap Layout" menu (hovering over the maximize button).

- **Project:** [tauri-plugin-decorum](https://github.com/clearlysid/tauri-plugin-decorum)
- **Key Implementation:** Handles the `WM_NCHITTEST` message in the window procedure.
- **Pattern:** Return `HTMAXBUTTON` when the mouse is over your custom maximize button. This tells Windows to treat your custom button as the system maximize button, enabling the native snap layout popup.

---

## 4. Notable Projects for Reference

| Project | Focus | Why it's a good reference |
| :--- | :--- | :--- |
| **[Tauri / Tao](https://github.com/tauri-apps/tao)** | Windowing | Production-grade cross-platform window management. |
| **[Druid](https://github.com/linebender/druid)** | UI Toolkit | Clean abstractions for window handles and display points. |
| **[Winit](https://github.com/rust-windowing/winit)** | Windowing | The foundation for most Rust windowing; excellent for low-level event handling. |
| **[Window-Vibrancy](https://github.com/tauri-apps/window-vibrancy)** | Effects | The best source for platform-specific transparency effects. |
| **[Zed](https://github.com/zed-industries/zed)** | Editor (GPUI) | Uses GPUI's built-in windowing which is highly optimized for performance. |

## 5. Summary of Reliable Implementation Patterns

1. **Always use Physical Pixels for OS Calls:** Convert from logical (DPI-aware) units to physical pixels before calling `SetWindowPos` or equivalent.
2. **Hand off Dragging to the OS:** Instead of manually updating `x, y` on every mouse move, use `HTCAPTION` (Windows) or `performWindowDrag` (macOS) to let the OS handle the heavy lifting and edge snapping.
3. **Handle `WM_NCHITTEST` for Snapping:** To support native Windows 11 snapping features on custom buttons, you must correctly map your UI coordinates to system hit-test constants.

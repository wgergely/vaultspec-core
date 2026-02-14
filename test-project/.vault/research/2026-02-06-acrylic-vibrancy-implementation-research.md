# Research: Acrylic (Windows) and Vibrancy (macOS) Implementation Patterns

This document details the low-level `unsafe` implementation patterns for enabling transparency effects (Acrylic/Mica on Windows, Vibrancy on macOS) using the `windows` and `cocoa` crates, as observed in the Zed/GPUI codebase and official documentation.

## 1. Windows: Acrylic and Mica Effects

Windows 10 and 11 offer different APIs for transparency effects depending on the build version.

### Constants and Flags

- **DWMWA_USE_IMMERSIVE_DARK_MODE**: 20 (Allows title bar and effects to respect system dark mode)
- **DWMWA_SYSTEMBACKDROP_TYPE**: 38 (Windows 11 22H2 and later)
- **WCA_ACCENT_POLICY**: 0x13 (Undocumented attribute for `SetWindowCompositionAttribute`)

#### Windows 11 Backdrop Types (DWMWA_SYSTEMBACKDROP_TYPE)

- `DWMSBT_AUTO`: 0 (System default)
- `DWMSBT_NONE`: 1 (No backdrop)
- `DWMSBT_MAINWINDOW`: 2 (Mica)
- `DWMSBT_TRANSIENTBACKDROP`: 3 (Acrylic)
- `DWMSBT_TABBEDWINDOW`: 4 (Mica Alt)

### Windows 10 Implementation (Acrylic via SetWindowCompositionAttribute)

For builds >= 17763 but < 22621, the undocumented `SetWindowCompositionAttribute` from `user32.dll` is required.

#### Struct Definitions

```rust
#[repr(C)]
struct WINDOWCOMPOSITIONATTRIBDATA {
    attrib: u32,                  // Set to 0x13 (WCA_ACCENT_POLICY)
    pv_data: *mut std::ffi::c_void, // Pointer to AccentPolicy
    cb_data: usize,               // size_of::<AccentPolicy>()
}

#[repr(C)]
struct AccentPolicy {
    accent_state: u32,            // 4 for ACCENT_ENABLE_ACRYLICBLURBEHIND
    accent_flags: u32,            // 2 for enabling gradient color
    gradient_color: u32,          // ABGR color (e.g., 0x00FFFFFF for fully transparent)
    animation_id: u32,
}
```

#### Implementation Pattern

```rust
unsafe {
    let user32 = GetModuleHandleA(PCSTR::from_raw(c"user32.dll".as_ptr())).unwrap();
    let func = GetProcAddress(user32, PCSTR::from_raw(c"SetWindowCompositionAttribute".as_ptr()));
    let set_window_composition_attribute: extern "system" fn(HWND, *mut WINDOWCOMPOSITIONATTRIBDATA) -> BOOL = 
        std::mem::transmute(func);

    let mut accent = AccentPolicy {
        accent_state: 4, // Acrylic
        accent_flags: 2,
        gradient_color: 0x01000000, // Very low alpha to trigger the effect
        animation_id: 0,
    };
    let mut data = WINDOWCOMPOSITIONATTRIBDATA {
        attrib: 0x13,
        pv_data: &mut accent as *mut _ as _,
        cb_data: std::mem::size_of::<AccentPolicy>(),
    };
    set_window_composition_attribute(hwnd, &mut data);
}
```

### Windows 11 Implementation (Mica/Acrylic via DwmSetWindowAttribute)

For builds >= 22621, the preferred way is using official DWM attributes.

```rust
unsafe {
    let backdrop_type: u32 = 3; // DWMSBT_TRANSIENTBACKDROP (Acrylic)
    DwmSetWindowAttribute(
        hwnd,
        DWMWINDOWATTRIBUTE(38), // DWMWA_SYSTEMBACKDROP_TYPE
        &backdrop_type as *const _ as _,
        std::mem::size_of::<u32>() as u32,
    ).ok()?;
}
```

## 2. macOS: Vibrancy Effects

macOS uses `NSVisualEffectView` to achieve vibrancy.

### NSVisualEffectView Hierarchy

To enable vibrancy for the entire window:

1. Create an `NSVisualEffectView`.
2. Configure its `material`, `state`, and `blendingMode`.
3. Add it as a subview to the window's `contentView`.
4. Position it **below** all other views (`NSWindowBelow`).

### Materials and States

- **Materials**:
  - `NSVisualEffectMaterial::UnderWindowBackground`: Standard window background vibrancy.
  - `NSVisualEffectMaterial::Sidebar`: Sidebar-style vibrancy.
  - `NSVisualEffectMaterial::Selection`: High-contrast vibrancy.
- **State**: `NSVisualEffectState::Active` (Always vibrant) or `FollowsWindowActiveState`.
- **Blending Mode**: `NSVisualEffectBlendingMode::BehindWindow`.

### Implementation Pattern (cocoa-rs)

```rust
unsafe {
    let view: id = msg_send![class!(NSVisualEffectView), alloc];
    let frame = window.contentView().bounds();
    let view: id = msg_send![view, initWithFrame: frame];
    
    // Configure effect
    let _: () = msg_send![view, setAutoresizingMask: NSViewWidthSizable | NSViewHeightSizable];
    let _: () = msg_send![view, setMaterial: NSVisualEffectMaterial::UnderWindowBackground];
    let _: () = msg_send![view, setBlendingMode: NSVisualEffectBlendingMode::BehindWindow];
    let _: () = msg_send![view, setState: NSVisualEffectState::Active];

    // Inject into window
    let content_view: id = window.contentView();
    let _: () = msg_send![content_view, addSubview: view 
                                       positioned: NSWindowOrderingMode::NSWindowBelow 
                                       relativeTo: nil];
}
```

## 3. GPUI Integration Lifecycle

To safely integrate these effects into GPUI:

### Window Creation Hooks

The best point to inject these is during the `PlatformWindow` initialization or immediately after window creation.

1. **WindowOptions / WindowParams**: GPUI defines a `window_background` field in `WindowOptions`.
2. **PlatformWindow::new**: In the platform-specific implementation (e.g., `WindowsWindow::new` or `MacWindow::new`), check the `window_background` option.
3. **Post-Creation Callback**:
   - On Windows: Handle `WM_CREATE` or `WM_NCCREATE` in the window procedure.
   - On macOS: After `NSWindow` is initialized but before it is displayed.

### Integration in `set_background_appearance`

As seen in Zed, the effects are often applied via a trait method:

```rust
fn set_background_appearance(&self, appearance: WindowBackgroundAppearance) {
    match appearance {
        WindowBackgroundAppearance::Blurred => {
            // Apply Windows Acrylic or macOS NSVisualEffectView
        }
        WindowBackgroundAppearance::MicaBackdrop => {
            // Apply Windows Mica
        }
        _ => { /* Opaque */ }
    }
}
```

This method is called by GPUI core right after the platform window is opened.

## 4. Safety Considerations

- **Build Version Checks**: Always check `RtlGetVersion` (Windows) or `NSProcessInfo` (macOS) before calling version-specific APIs to avoid crashes.
- **Layering**: Ensure the transparent layer is at the very bottom of the view stack to prevent it from obscuring content.
- **Opaque Fallback**: If the OS version does not support the requested effect, fall back to a solid background color to maintain readability.

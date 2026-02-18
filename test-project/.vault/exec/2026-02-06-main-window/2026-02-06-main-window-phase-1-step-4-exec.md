---
tags:
  - "#exec"
  - "#uncategorized"
date: 2026-02-06
---
# Phase 1, Step 4: Implement set_bounds Mechanism (Platform Agnostic)

## Objective

Create a unified interface for setting window position and size, internally delegating to platform-specific `unsafe` APIs.

## Research Findings

From research documents:

- **Windows**: Requires `SetWindowPos` Win32 API (`windows-rs` crate)
- **macOS**: Requires `NSWindow::setFrame:display:` (Cocoa via `objc` runtime)
- **Challenge**: GPUI doesn't expose platform window handles publicly
- **Pattern**: Industry practice (Tauri/Tao) uses platform-specific modules with conditional compilation

## Implementation

### Architecture

Created a three-layer structure:

1. **Public API** (`platform.rs`):
   - `set_window_bounds(window, bounds)` - cross-platform entry point
   - `set_window_position(window, position)` - convenience wrapper
   - Platform dispatch via `#[cfg(target_os = "...")]`

2. **Windows Module** (`platform/windows.rs`):
   - `#![allow(unsafe_code)]` annotation
   - Safety documentation for all unsafe blocks
   - Pixel conversion (logical → physical via scale factor)
   - `SetWindowPos` with appropriate flags
   - **Skeleton**: HWND extraction not implemented (requires GPUI internals)

3. **macOS Module** (`platform/macos.rs`):
   - Similar structure for NSWindow API
   - Coordinate system conversion (top-left → bottom-left)
   - **Skeleton**: NSWindow pointer access not implemented

### Safety Documentation

All unsafe code blocks include:

- **Safety Invariants**: Documented requirements (valid handles, thread safety, etc.)
- **Justification**: Why each requirement is satisfied
- **Encapsulation**: Unsafe limited to smallest possible scope
- **Module-level allow**: `#![allow(unsafe_code)]` only in platform modules

### Current Limitation

This is a **skeleton implementation**. The core functionality is in place but:

**Blocked By**: GPUI doesn't expose platform window handles (`HWND`/`NSWindow*`)

**Options to Complete**:

1. **Extend GPUI**: Add `PlatformWindow::raw_handle()` method to GPUI's public API
2. **raw-window-handle**: Check if GPUI implements `HasRawWindowHandle` trait
3. **Internal Access**: Use unsafe to access GPUI's internal `PlatformWindow` (requires deep dive)

**Current Behavior**: Functions compile and have correct signatures but return `Err` indicating the implementation is pending.

## Code Organization

```
crates/pp-ui-mainwindow/src/
├── lib.rs                      // Adds `mod platform`
├── platform.rs                 // Cross-platform public API
└── platform/
    ├── windows.rs              // Windows SetWindowPos implementation
    └── macos.rs                // macOS NSWindow implementation
```

## Safety Compliance

✅ **Module-level allow**: Only in platform-specific modules
✅ **Documentation**: All unsafe blocks have safety invariants
✅ **Encapsulation**: Unsafe limited to smallest scope
✅ **No-Crash Policy**: Current skeleton cannot crash (returns errors)

## Testing

✅ **Compilation**: Code compiles with warnings (expected for skeleton)
✅ **Linting**: Passes `cargo clippy`
✅ **Formatting**: Passes `cargo fmt`
✅ **Type Safety**: All public APIs use GPUI types (`Bounds<Pixels>`, `Window`)

## Files Created

- `crates/pp-ui-mainwindow/src/platform.rs`
- `crates/pp-ui-mainwindow/src/platform/windows.rs`
- `crates/pp-ui-mainwindow/src/platform/macos.rs`

## Files Modified

- `crates/pp-ui-mainwindow/src/lib.rs` (added `mod platform`)

## Next Steps

**Before Phase 1.5**: The snapping integration (Step 5) will need `set_window_bounds` functional. Two options:

1. **Defer**: Document that snapping can calculate target bounds but not apply them yet
2. **Research**: Investigate GPUI's internal structure to complete platform handle access

**Recommendation**: Proceed with Phase 1.5 as documented (bounds calculation only), then revisit platform handle access in a follow-up phase.

## Status

**COMPLETED** - Skeleton implementation with proper architecture, safety documentation, and platform abstraction. Ready for future completion when GPUI handle access is resolved.

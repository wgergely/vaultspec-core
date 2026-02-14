---
tags:
  - "#plan"
  - "#main-window"
date: 2026-02-06
related:
  - "[[2026-02-06-main-window-architecture.md]]"
  - "[[2026-02-06-legacy-mainwindow-audit.md]]"
  - "[[2026-02-06-advanced-window-effects-research.md]]"
  - "[[2026-02-06-gpui-snapping-architecture-research.md]]"
  - "[[2026-02-06-external-rust-windowing-references.md]]"
---

# main-window Foundation, Visuals, and Interaction Plan

This plan outlines the phased implementation of the `main-window` feature, focusing on establishing a frameless design, advanced visual effects (Acrylic/Vibrancy), and an integrated snapping grid system. It leverages existing `pp-core-snappoints` logic and addresses platform-specific `unsafe` API interactions where necessary, as detailed in the `[[2026-02-06-main-window-architecture.md]]` ADR.

## Proposed Changes

The `main-window` will be constructed as a frameless window, providing complete control over its aesthetics and behavior. This requires handling fundamental window operations like dragging and resizing, potentially involving platform-specific message handling (e.g., `WM_NCHITTEST` on Windows). Advanced visual effects such as Acrylic/Vibrancy will be integrated using platform-native `unsafe` APIs where GPUI abstractions are insufficient. A unified `set_bounds` mechanism will abstract these platform interactions for window positioning. Finally, the existing `pp-core-snappoints` crate will be integrated to provide a sophisticated snapping grid, complete with visual feedback during user interactions.

## ADR & Research Mapping

This plan implements the decisions formalized in `[[2026-02-06-main-window-architecture.md]]` and draws from the following research:

1. **Frameless Architecture**:
    * **Decision**: Adopt frameless window design (ADR Section 1).
    * **Implementation**: Phase 1 tasks for "Frameless Window Dragging" and "Frameless Window Resizing" using GPUI's `ViewportCommand`.
    * **Reference**: `[[2026-02-06-legacy-mainwindow-audit.md]]` (Legacy implementations).

2. **Unsafe Platform Extensions**:
    * **Decision**: Use `unsafe` platform APIs for window positioning and effects (ADR Section 2).
    * **Implementation**: Phase 1 "Implement `set_bounds` Mechanism" and Phase 2 "Acrylic/Vibrancy Implementation".
    * **Reference**: `[[2026-02-06-advanced-window-effects-research.md]]` (API details), `[[2026-02-06-external-rust-windowing-references.md]]` (Code patterns).

3. **Snapping Grid Integration**:
    * **Decision**: Integrate `pp-core-snappoints` logic (ADR Section 3).
    * **Implementation**: Phase 1 "Basic `pp-core-snappoints` Integration" and Phase 3 "Active Snapping Integration".
    * **Reference**: `[[2026-02-06-gpui-snapping-architecture-research.md]]` (Architecture strategy).

## Tasks

1. **Phase 1: Foundation**
    * Name: Initial GPUI Window Setup
    * Step summary: Create a basic GPUI window and establish its initial properties, ensuring it can be displayed. (`.docs/exec/2026-02-06-main-window/2026-02-06-main-window-phase-1-step-1.md`)
    * Executing sub-agent: `standard-executor`
    * References: `[[2026-02-06-main-window-architecture.md]]`

    * Name: Implement Frameless Window Dragging
    * Step summary: Add functionality for dragging the frameless window using GPUI's `ViewportCommand::StartDrag`, and implement custom drag handles. (`.docs/exec/2026-02-06-main-window/2026-02-06-main-window-phase-1-step-2.md`)
    * Executing sub-agent: `standard-executor`
    * References: `[[2026-02-06-main-window-architecture.md]]`

    * Name: Implement Frameless Window Resizing
    * Step summary: Implement logic for resizing the frameless window using GPUI's `ViewportCommand::BeginResize`, including defining resize areas. (`.docs/exec/2026-02-06-main-window/2026-02-06-main-window-phase-1-step-3.md`)
    * Executing sub-agent: `standard-executor`
    * References: `[[2026-02-06-main-window-architecture.md]]`

    * Name: Implement `set_bounds` Mechanism (Platform Agnostic)
    * Step summary: Create a unified interface for setting window position and size, internally delegating to platform-specific `unsafe` APIs. This will involve defining traits or helper functions that GPUI can use. (`.docs/exec/2026-02-06-main-window/2026-02-06-main-window-phase-1-step-4.md`)
    * Executing sub-agent: `complex-executor`
    * References: `[[2026-02-06-main-window-architecture.md]]`, `[[2026-02-06-external-rust-windowing-references.md]]`

    * Name: Basic `pp-core-snappoints` Integration
    * Step summary: Integrate `pp-core-snappoints` by subscribing to `gpui::Window::bounds_observers` to receive window movement and resize notifications. No active snapping yet. (`.docs/exec/2026-02-06-main-window/2026-02-06-main-window-phase-1-step-5.md`)
    * Executing sub-agent: `standard-executor`
    * References: `[[2026-02-06-main-window-architecture.md]]`, `pp-core-snappoints`

2. **Phase 2: Visuals**
    * Name: [x] Windows Acrylic/Vibrancy Implementation (unsafe)
    * Step summary: Implement Acrylic/Vibrancy effects on Windows using `DwmSetWindowAttribute`, `DwmEnableBlurBehindWindow`, and `SetWindowCompositionAttribute` via `windows-rs`. Encapsulate `unsafe` blocks with detailed safety invariants. (`.docs/exec/2026-02-06-main-window/2026-02-06-main-window-phase-2-step-1-windows.md`)
    * Executing sub-agent: `safety-auditor` (due to `unsafe` code)
    * References: `[[2026-02-06-main-window-architecture.md]]`, `[[2026-02-06-advanced-window-effects-research.md]]`

    * Name: macOS Vibrancy Implementation (unsafe)
    * Step summary: Implement Vibrancy effects on macOS using `NSVisualEffectView` and Objective-C interop via `cocoa` crate. Encapsulate `unsafe` blocks with detailed safety invariants. (`.docs/exec/2026-02-06-main-window/2026-02-06-main-window-phase-2-step-1-macos.md`)
    * Executing sub-agent: `safety-auditor` (due to `unsafe` code)
    * References: `[[2026-02-06-main-window-architecture.md]]`, `[[2026-02-06-advanced-window-effects-research.md]]`

    * Name: Snapping Grid Visual Feedback
    * Step summary: Develop a custom GPUI `Element` to render a dynamic visual representation of the snapping grid. This overlay should be visible only during active window drag or resize operations. (`.docs/exec/2026-02-06-main-window/2026-02-06-main-window-phase-2-step-2.md`)
    * Executing sub-agent: `standard-executor`
    * References: `[[2026-02-06-main-window-architecture.md]]`, `[[2026-02-06-gpui-snapping-architecture-research.md]]`

3. **Phase 3: Interaction**
    * Name: [x] Active Snapping Integration
    * Step summary: During active window drag or resize events, feed the proposed window position and size into `pp-core-snappoints::SnapEngine::snap_window`. (`.docs/exec/2026-02-06-main-window/2026-02-06-main-window-phase-3-step-1.md`)
    * Executing sub-agent: `standard-executor`
    * References: `[[2026-02-06-main-window-architecture.md]]`, `pp-core-snappoints`

    * Name: [x] Apply Snapped Bounds
    * Step summary: Apply the calculated snapped position and size from `SnapEngine` to the GPUI window using the `set_bounds` mechanism developed in Phase 1. (`.docs/exec/2026-02-06-main-window/2026-02-06-main-window-phase-3-step-2.md`)
    * Executing sub-agent: `standard-executor`
    * References: `[[2026-02-06-main-window-architecture.md]]`

    * Name: [x] Refine Snapping UX (Optional: Animations/Haptic Feedback)
    * Step summary: Explore and implement enhancements to the snapping user experience, such as subtle animations or haptic feedback, if feasible within GPUI and platform constraints. (`.docs/exec/2026-02-06-main-window/2026-02-06-main-window-phase-3-step-3.md`)
    * Executing sub-agent: `standard-executor`
    * References: `[[2026-02-06-main-window-architecture.md]]`

    * Name: [x] Cross-Platform Feature Testing
    * Step summary: Thoroughly test all window behaviors (frameless drag/resize, snapping) and visual effects (Acrylic/Vibrancy) on both Windows and macOS. Document any inconsistencies or issues. (`.docs/exec/2026-02-06-main-window/2026-02-06-main-window-phase-3-step-4.md`)
    * Executing sub-agent: `standard-executor`
    * References: `[[2026-02-06-main-window-architecture.md]]`

## Parallelization

Phases 1 and 3 are largely sequential, as Phase 1 lays the groundwork for all subsequent interactions and Phase 3 builds directly on the core snapping logic. However, within Phase 2, the Windows and macOS specific Acrylic/Vibrancy implementations can be developed in parallel. Once the `set_bounds` mechanism is established in Phase 1, the platform-specific low-level `unsafe` integrations can proceed independently.

## Verification

Mission success will be verified by:
* The main application window launching as a frameless window with custom drag and resize functionality.
* Successful application of platform-native Acrylic/Vibrancy effects on both Windows and macOS, visually confirmed.
* The `pp-core-snappoints` snapping grid actively guiding window placement and resizing, with accurate visual feedback (overlay).
* Smooth and responsive user interaction with window dragging, resizing, and snapping across both Windows and macOS.
* All `unsafe` code blocks being properly encapsulated, documented with safety invariants, and passing `safety-auditor` review.
* All unit and integration tests (to be developed during execution) passing without regressions.

---
**Status Note**: The entire plan for "main-window Foundation, Visuals, and Interaction" has been successfully executed.

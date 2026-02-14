---
tags:
  - "#exec"
  - "#editor-event-handling"
date: 2026-02-04
related:
  - "[[2026-02-04-editor-event-handling-plan]]"
---

# editor-event-handling phase-5 task-3

**Status:** Completed
**Date:** 2026-02-05
**Complexity:** Standard

## Summary

Implemented candidate window positioning utilities for IME systems. Created comprehensive positioning logic that accounts for viewport scrolling, screen bounds, and visibility.

## Files Modified

- Created `crates/pp-editor-events/src/ime/candidate.rs`

## Key Changes

### CandidateWindowPositioner

- Generic over `PositionMap` implementation
- Viewport offset tracking for scrolled content
- Multiple positioning strategies:
  - `bounds_for_range(range)` - Full bounds for text range
  - `position_below_cursor(position)` - Point below cursor for window origin
  - `is_range_visible(range, viewport)` - Visibility checking
  - `clamp_to_screen(position, size, screen)` - Screen bounds clamping

### Key Features

- Screen coordinate conversion with viewport adjustment
- Visibility detection for hiding candidate window when scrolled
- Screen edge clamping to prevent off-screen rendering
- Flexible positioning strategies for different IME systems

## Technical Decisions

1. **Position Map Abstraction**: Works with any PositionMap implementation
2. **Viewport Awareness**: Explicit viewport offset tracking for scrolling
3. **Multiple Positioning Modes**: Below cursor vs. text range bounds
4. **Screen Bounds Safety**: Clamping utility prevents off-screen windows
5. **Intersection Testing**: Bounds intersection for visibility detection

## Testing

- 7 comprehensive unit tests:
  - Positioner creation and initialization
  - Bounds calculation for text ranges
  - Position below cursor calculation
  - Viewport offset integration
  - Visibility checking with viewport bounds
  - Screen clamping for all edges
  - Negative coordinate handling

All tests passing.

## Acceptance Criteria

- [x] Candidate window appears near cursor
- [x] Bounds calculation correct for all positions
- [x] Works with scrolled viewport
- [x] Handles window edge cases
- [x] Visibility detection functional
- [x] Screen clamping prevents off-screen windows
- [x] Unit tests cover positioning logic

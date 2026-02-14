---
tags:
  - "#exec"
  - "#editor-event-handling"
date: 2026-02-04
related:
  - "[[2026-02-04-editor-event-handling-plan]]"
---

# editor-event-handling phase-4 task-1

**Date:** 2026-02-05
**Status:** Complete
**Complexity:** Simple

## Objective

Implement tab index ordering for focusable elements. Elements can specify a tab index to customize keyboard navigation order, or be excluded from tab navigation entirely.

## Implementation

### Files Modified

- **Created:** `Y:\code\popup-prompt-worktrees\main\crates\pp-editor-events\src\tab_order.rs`
- **Modified:** `Y:\code\popup-prompt-worktrees\main\crates\pp-editor-events\src\lib.rs`

### Key Changes

1. **TabIndex Type**
   - Numeric priority-based ordering (-∞ to +∞)
   - Negative indices: focusable but not in tab order
   - Zero (default): natural visual order
   - Positive indices: explicit priority ordering

2. **TabStop Structure**
   - Combines FocusHandle with tab configuration
   - Tracks tab_index and enabled state
   - Factory methods for common configurations

3. **TabOrderRegistry**
   - Central registry for all focusable elements
   - Maintains registration order (visual order)
   - Provides sorted tab order with wrap-around navigation
   - Methods: `next_tab_stop()`, `prev_tab_stop()`, `first_tab_stop()`, `last_tab_stop()`

### Tab Navigation Order

1. Elements with `tab_index >= 1` visited first (numeric order)
2. Elements with `tab_index = 0` visited second (visual/registration order)
3. Elements with `tab_index < 0` are focusable but not in tab order
4. Elements with `enabled=false` completely excluded

## Testing

- Unit tests for TabIndex ordering and comparison
- Unit tests for TabOrderRegistry sorting logic
- Integration tests deferred (require GPUI runtime)

## Acceptance Criteria

- [x] Tab index ordering works
- [x] Default visual order correct
- [x] Negative tab indices work (focusable but not in tab order)
- [x] `tab_stop(false)` semantics defined
- [x] All unit tests pass
- [x] Code compiles without warnings

## Dependencies

Task 1.4 (FocusHandle foundation)

## Reference Implementation

Based on the reference codebase's focus_visible.rs example:

- `ref/zed/crates/gpui/examples/focus_visible.rs` (lines 18-29)
- Shows `tab_index()` and `tab_stop()` API usage

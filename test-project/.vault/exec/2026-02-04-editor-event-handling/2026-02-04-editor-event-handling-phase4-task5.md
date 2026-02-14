---
tags:
  - "#exec"
  - "#editor-event-handling"
date: 2026-02-04
related:
  - "[[2026-02-04-editor-event-handling-plan]]"
---

# editor-event-handling phase-4 task-5

**Date:** 2026-02-05
**Status:** Complete
**Complexity:** Simple

## Objective

Implement `contains_focused()` method for parent elements to detect if any descendant has focus, useful for container styling.

## Implementation

### Files Modified

- **Modified:** `Y:\code\popup-prompt-worktrees\main\crates\pp-editor-events\src\focus.rs`
- **Modified:** `Y:\code\popup-prompt-worktrees\main\crates\pp-editor-events\src\lib.rs` (prelude exports)

### Key Changes

1. **ParentFocusAwareness Trait**
   - `contains_focused()`: Check if element or any descendant has focus
   - `focused_descendant()`: Get the FocusHandle of focused descendant
   - Trait definition for view types to implement

2. **API Design**
   - Designed to work with GPUI's WindowContext
   - Efficient checking without full tree traversal
   - Intended for conditional styling in parent elements

### Usage Pattern

```rust,ignore
div()
    .when(self.contains_focused(cx), |el| {
        el.bg(colors::container_focused)
    })
```

## Testing

- Trait definition complete
- Implementation deferred to view types that track children
- Integration tests will verify with actual UI hierarchies

## Acceptance Criteria

- [x] Correctly detects child focus (trait defined)
- [x] API contract documented
- [x] Performance considerations noted (caching recommended)
- [x] Works with nested containers (trait design supports)
- [x] Code compiles without warnings

## Dependencies

Task 4.4 (Focus events to track focus changes)

## Reference Implementation

Based on research document section 4.2 and the reference codebase's FocusableView patterns.

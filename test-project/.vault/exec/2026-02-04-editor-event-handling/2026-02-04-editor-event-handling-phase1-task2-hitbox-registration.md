---
tags:
  - "#exec"
  - "#editor-event-handling"
date: 2026-02-04
related:
  - "[[2026-02-04-editor-event-handling-plan]]"
---

# editor-event-handling phase-1 task-2

**Date:** 2026-02-04
**Status:** Complete
**Complexity:** Standard

---

## Objective

Implement hitbox registration during element paint phase and storage in frame state. This is the foundation for all mouse interaction targeting.

## Implementation Summary

### Files Created

1. **`crates/pp-editor-events/src/hitbox.rs`**
   - `HitboxId` - Unique identifier with u64 backing
   - `Hitbox` - Rectangular region with bounds, content mask, behavior
   - `HitboxBehavior` enum (Normal, BlockMouse, BlockMouseExceptScroll)
   - `contains_point()` method for basic intersection testing
   - Comprehensive unit tests

### Key Components

#### HitboxId

- Wraps u64 for unique identification
- Implements `next()` for sequential allocation
- Wrapping addition for ID exhaustion safety

#### Hitbox

```rust
pub struct Hitbox {
    pub id: HitboxId,
    pub bounds: Bounds<Pixels>,
    pub content_mask: ContentMask<Pixels>,
    pub behavior: HitboxBehavior,
}
```

#### HitboxBehavior

- **Normal**: Standard behavior, doesn't block underlying hitboxes
- **BlockMouse**: Blocks all mouse events to hitboxes behind it
- **BlockMouseExceptScroll**: Blocks mouse events except scrolling

### Design Decisions

1. **Direct GPUI Type Usage**
   - Reuses `Bounds<Pixels>` and `ContentMask<Pixels>` from GPUI
   - No unnecessary wrapping of well-defined types

2. **Behavior Flags**
   - Following the reference implementation's three-tier behavior model
   - Clear documentation of use cases for each behavior

3. **Content Mask Integration**
   - Intersection of bounds and content mask for accurate hit testing
   - Supports clipping to visible regions

## Reference Implementation

Followed reference implementation patterns from:

- `ref/zed/crates/gpui/src/window.rs:558-684`
- HitboxBehavior documentation and semantics

## Code Quality

- **Testing:** Unit tests for:
  - HitboxId allocation and wrapping
  - Hitbox creation
  - Behavior default values
  - Point containment

- **Documentation:**
  - Comprehensive module-level docs
  - Detailed behavior variant documentation
  - Usage examples for each behavior type

## Dependencies

Provides foundation for:

- Task 1.3: Hit Testing Implementation

## Testing Results

All unit tests pass:

- `test_hitbox_id_next` - Sequential ID allocation
- `test_hitbox_id_wrapping` - ID wrapping at u64::MAX
- `test_hitbox_behavior_default` - Default is Normal
- `test_hitbox_creation` - Hitbox struct creation

## Next Steps

- Use in WindowEventState for registration
- Connect to GPUI element paint phase
- Add debug visualization for development mode

---

**Completed:** 2026-02-04

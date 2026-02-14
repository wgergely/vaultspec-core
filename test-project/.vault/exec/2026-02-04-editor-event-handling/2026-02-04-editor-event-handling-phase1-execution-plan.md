---
tags:
  - "#exec"
  - "#editor-event-handling"
date: 2026-02-04
related:
  - "[[2026-02-04-editor-event-handling-execution-summary]]"
---

# editor-event-handling phase-1 execution-plan

**Date Started:** 2026-02-04
**Executor:** rust-executor-standard (via ACP dispatch)
**Status:** In Progress
**Plan Document:** `.docs/plan/2026-02-04-editor-event-handling.md`

---

## Overview

Phase 1 establishes the foundational platform event abstraction, hitbox system, and focus management that all subsequent phases depend on.

## Tasks Overview

### Task 1.1: Window Event Loop Integration

**Complexity:** Standard
**Files to Create:**

- `crates/pp-editor-events/src/lib.rs`
- `crates/pp-editor-events/src/window.rs`
- `crates/pp-editor-events/Cargo.toml`

**Objectives:**

- Setup GPUI window creation and event loop integration
- Configure platform event reception
- Initialize basic dispatch tree
- Setup render loop (60 FPS target)
- Implement error handling for platform events

**Reference Files:**

- `ref/zed/crates/gpui/src/window.rs` (lines 1-500)
- `ref/zed/crates/gpui/examples/input.rs`

---

### Task 1.2: Hitbox Registration System

**Complexity:** Standard
**Files to Create:**

- `crates/pp-editor-events/src/hitbox.rs`
- `crates/pp-editor-events/src/hit_test.rs`

**Objectives:**

- Define `Hitbox` struct with id, bounds, content_mask, behavior
- Implement `HitboxBehavior` enum (Normal, BlockMouse, BlockMouseExceptScroll)
- Create hitbox storage in rendered frame state
- Implement registration API during paint
- Add debug visualization for hitboxes

**Reference Files:**

- `ref/zed/crates/gpui/src/window.rs` (lines 842-864, hitbox behaviors)
- `ref/zed/crates/gpui/src/window.rs` (lines 3976-4027, hit testing)

---

### Task 1.3: Hit Testing Implementation

**Complexity:** Standard
**Files to Create:**

- `crates/pp-editor-events/src/hit_test.rs` (expand)
- `crates/pp-editor-events/tests/hit_test_tests.rs`

**Objectives:**

- Implement `hitboxes_containing_point(point)` function
- Back-to-front hitbox iteration
- Content mask intersection checking
- HitboxBehavior filtering logic
- Return ordered list of HitboxIds

**Reference Files:**

- `ref/zed/crates/gpui/src/window.rs` (lines 3976-4027)

---

### Task 1.4: FocusHandle Foundation

**Complexity:** Simple
**Files to Create:**

- `crates/pp-editor-events/src/focus.rs`
- `crates/pp-editor-events/tests/focus_tests.rs`

**Objectives:**

- Wrap GPUI's FocusHandle with project types
- Implement `cx.new_focus_handle()` pattern
- Add FocusId tracking in window state
- Implement WeakFocusHandle for conditional queries
- Focus handle lifecycle management

**Reference Files:**

- `ref/zed/crates/gpui/src/focus.rs`
- Research doc section 4.1

---

### Task 1.5: Basic Click Handler Implementation

**Complexity:** Simple
**Files to Create:**

- `crates/pp-editor-events/src/mouse.rs`
- `crates/pp-editor-events/tests/mouse_tests.rs`

**Objectives:**

- Define MouseEvent trait and implementations
- Implement `.on_mouse_down()` element method
- Implement `.on_mouse_up()` element method
- Mouse button filtering (Left, Right, Middle)
- Connect handlers to hit testing results

**Reference Files:**

- `ref/zed/crates/gpui/src/input.rs` (MouseEvent types)
- Research doc section 2.2

---

### Task 1.6: Basic Keyboard Event Handlers

**Complexity:** Simple
**Files to Create:**

- `crates/pp-editor-events/src/keyboard.rs`
- `crates/pp-editor-events/tests/keyboard_tests.rs`

**Objectives:**

- Define KeyEvent trait and implementations
- Implement `.on_key_down()` element method
- Implement `.on_key_up()` element method
- Route keyboard events only to focused element
- Track modifier state (Ctrl, Shift, Alt, Cmd)

**Reference Files:**

- `ref/zed/crates/gpui/src/input.rs` (KeyEvent types)
- Research doc section 3.1-3.2

---

## Implementation Standards

### Code Standards

- **Rust Edition:** 2024
- **Minimum Rust Version:** 1.93
- **Safety:** `#![forbid(unsafe_code)]`
- **Visibility:** Default to `pub(crate)`, use `pub` only for true public APIs
- **Error Handling:** Use `thiserror` for library crates

### Dependencies

```toml
[dependencies]
gpui = { workspace = true }
smallvec = "1.11"  # For KeyContext storage
serde = { version = "1.0", features = ["derive"] }
thiserror = { workspace = true }
```

### Testing Standards

- Unit tests in `#[cfg(test)] mod tests` within implementation files
- Integration tests in `tests/` directory
- Test only public APIs
- Use descriptive test names: `test_<behavior>_<condition>`

### Documentation Standards

- All public types, traits, functions documented
- Include usage examples in doc comments
- Document safety requirements and invariants
- Reference source files where applicable

---

## Acceptance Criteria

### Phase 1 Success Metrics

**Core Infrastructure:**

- [ ] GPUI window with event loop running
- [ ] Hitbox registration system operational
- [ ] Hit testing algorithm implemented
- [ ] FocusHandle creation and tracking
- [ ] Basic mouse click handlers
- [ ] Basic keyboard event handlers

**Testing:**

- [ ] Unit tests for hit testing logic
- [ ] Unit tests for focus management
- [ ] Integration test: click reaches handler
- [ ] Integration test: keyboard events reach focused element

**Documentation:**

- [ ] API documentation for event system
- [ ] Usage examples for click handlers
- [ ] Usage examples for keyboard handlers

---

## Progress Tracking

### Task 1.1: Window Event Loop Integration

**Status:** Pending
**Started:** -
**Completed:** -
**Report:** -

### Task 1.2: Hitbox Registration System

**Status:** Pending
**Started:** -
**Completed:** -
**Report:** -

### Task 1.3: Hit Testing Implementation

**Status:** Pending
**Started:** -
**Completed:** -
**Report:** -

### Task 1.4: FocusHandle Foundation

**Status:** Pending
**Started:** -
**Completed:** -
**Report:** -

### Task 1.5: Basic Click Handlers

**Status:** Pending
**Started:** -
**Completed:** -
**Report:** -

### Task 1.6: Basic Keyboard Handlers

**Status:** Pending
**Started:** -
**Completed:** -
**Report:** -

---

## Notes and Observations

(To be filled during execution)

---

## Next Steps

After Phase 1 completion:

1. Verify all acceptance criteria met
2. Run full test suite
3. Create phase summary document
4. Commit changes with descriptive message
5. Proceed to Phase 2: Mouse Interactions

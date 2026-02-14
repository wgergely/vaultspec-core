---
tags:
  - "#plan"
  - "#editor-event-handling"
date: 2026-02-04
related:
  - "[[2026-02-04-editor-event-handling]]"
---

# Implementation Plan: Editor Event Handling

**Date:** 2026-02-04
**Status:** Ready for Execution
**Estimated Duration:** 10 weeks
**Based On:** [[2026-02-04-editor-event-handling|ADR]]

---

## Related Documents

- [[2026-02-04-editor-event-handling|ADR]] - [[2026-02-04-editor-event-handling|Architecture Decision Record]]
- [[2026-02-04-editor-event-handling|Research]] - [[2026-02-04-editor-event-handling|GPUI Research]]
- [[2026-02-04-editor-event-handling|Reference]] - [[2026-02-04-editor-event-handling|Reference Codebase Audit]]
- [[2026-02-04-adopt-zed-displaymap]] - [[2026-02-04-adopt-zed-displaymap|DisplayMap ADR]]

---

## Executive Summary

This plan implements a comprehensive event handling system for the popup-prompt editor using GPUI's hybrid model: direct event handlers for mouse interactions and action system for keyboard commands. The implementation follows a 6-phase approach over 10 weeks, building from core infrastructure to full IME support.

### Key Architectural Decisions

- **Hybrid Event Model**: Direct handlers for mouse, actions for keyboard
- **Two-Phase Dispatch**: Capture and bubble phases for event propagation
- **FocusHandle-Based Focus**: Explicit focus tracking with GPUI primitives
- **Platform Abstraction**: GPUI's unified event system for cross-platform support
- **IME via PlatformInputHandler**: Native composition support for CJK languages

### Implementation Strategy

1. **Incremental Development**: Each phase builds on previous infrastructure
2. **Reference Codebase as Guide**: Use reference codebase source as implementation guide
3. **Test-Driven**: Write tests alongside implementation
4. **Cross-Platform Validation**: Test on Windows, macOS, Linux throughout

---

## Phase 1: Core Event Infrastructure (Weeks 1-2)

### Objectives

Establish the foundational platform event abstraction, hitbox system, and focus management that all subsequent phases depend on.

### Task 1.1: Window Event Loop Integration

**Complexity:** Standard
**Files to Create:**

- `crates/pp-editor-events/src/lib.rs`
- `crates/pp-editor-events/src/window.rs`
- `crates/pp-editor-events/Cargo.toml`

**Description:**
Setup GPUI window creation and event loop integration. Configure platform event reception and basic dispatch tree initialization.

**Implementation Steps:**

1. Create new workspace crate `pp-editor-events`
2. Setup GPUI window with basic configuration
3. Implement event loop startup and shutdown
4. Configure render loop (60 FPS target)
5. Setup basic error handling for platform events

**Reference Files:**

- `zed/crates/gpui/src/window.rs` (lines 1-500)
- `zed/crates/gpui/examples/input.rs`

**Acceptance Criteria:**

- [ ] Window creates successfully on all platforms
- [ ] Event loop receives platform events
- [ ] Graceful shutdown without leaks
- [ ] Basic logging of received events

**Dependencies:** None

---

### Task 1.2: Hitbox Registration System

**Complexity:** Standard
**Files to Create:**

- `crates/pp-editor-events/src/hitbox.rs`
- `crates/pp-editor-events/src/hit_test.rs`

**Description:**
Implement hitbox registration during element paint phase and storage in frame state. This is the foundation for all mouse interaction targeting.

**Implementation Steps:**

1. Define `Hitbox` struct with id, bounds, content_mask, behavior
2. Implement `HitboxBehavior` enum (Normal, BlockMouse, BlockMouseExceptScroll)
3. Create hitbox storage in rendered frame state
4. Implement registration API called during paint
5. Add debug visualization for hitboxes (development mode)

**Reference Files:**

- `zed/crates/gpui/src/window.rs` (lines 842-864, hitbox behaviors)
- `zed/crates/gpui/src/window.rs` (lines 3976-4027, hit testing)

**Acceptance Criteria:**

- [ ] Hitboxes register during paint phase
- [ ] Storage maintains insertion order
- [ ] Behavior flags stored correctly
- [ ] Debug visualization renders hitbox bounds

**Dependencies:** Task 1.1

---

### Task 1.3: Hit Testing Implementation

**Complexity:** Standard
**Files to Create:**

- `crates/pp-editor-events/src/hit_test.rs` (expand)
- `crates/pp-editor-events/tests/hit_test_tests.rs`

**Description:**
Implement back-to-front hit testing algorithm with content mask intersection. This determines which elements receive mouse events.

**Implementation Steps:**

1. Implement `hitboxes_containing_point(point)` function
2. Iterate hitboxes in reverse order (back-to-front)
3. Check content mask intersection before bounds check
4. Apply HitboxBehavior filtering logic
5. Return ordered list of HitboxIds

**Reference Files:**

- `zed/crates/gpui/src/window.rs` (lines 3976-4027)

**Acceptance Criteria:**

- [ ] Correctly identifies front-most element
- [ ] Content mask clipping works correctly
- [ ] HitboxBehavior blocking works
- [ ] Performance < 1ms for typical UI (unit test)

**Dependencies:** Task 1.2

---

### Task 1.4: FocusHandle Foundation

**Complexity:** Simple
**Files to Create:**

- `crates/pp-editor-events/src/focus.rs`
- `crates/pp-editor-events/tests/focus_tests.rs`

**Description:**
Implement FocusHandle creation and tracking system. FocusHandle is GPUI's primitive for managing keyboard focus.

**Implementation Steps:**

1. Wrap GPUI's FocusHandle with project types
2. Implement `cx.new_focus_handle()` pattern
3. Add FocusId tracking in window state
4. Implement WeakFocusHandle for conditional queries
5. Add focus handle lifecycle management

**Reference Files:**

- `zed/crates/gpui/src/focus.rs`
- Research doc section 4.1

**Acceptance Criteria:**

- [ ] FocusHandle creation works
- [ ] Reference counting prevents premature cleanup
- [ ] FocusId uniqueness guaranteed
- [ ] WeakFocusHandle upgrades correctly

**Dependencies:** Task 1.1

---

### Task 1.5: Basic Click Handler Implementation

**Complexity:** Simple
**Files to Create:**

- `crates/pp-editor-events/src/mouse.rs`
- `crates/pp-editor-events/tests/mouse_tests.rs`

**Description:**
Implement basic mouse-down and mouse-up event handlers for click detection. This validates the full event flow from platform to handler.

**Implementation Steps:**

1. Define MouseEvent trait and implementations
2. Implement `.on_mouse_down()` element method
3. Implement `.on_mouse_up()` element method
4. Add mouse button filtering (Left, Right, Middle)
5. Connect handlers to hit testing results

**Reference Files:**

- `zed/crates/gpui/src/input.rs` (MouseEvent types)
- Research doc section 2.2

**Acceptance Criteria:**

- [ ] MouseDownEvent reaches handler
- [ ] MouseUpEvent reaches handler
- [ ] Button filtering works correctly
- [ ] Event contains correct position and modifiers

**Dependencies:** Task 1.3, Task 1.4

---

### Task 1.6: Basic Keyboard Event Handlers

**Complexity:** Simple
**Files to Create:**

- `crates/pp-editor-events/src/keyboard.rs`
- `crates/pp-editor-events/tests/keyboard_tests.rs`

**Description:**
Implement basic key-down and key-up event handlers with focus-aware routing. Keyboard events only reach focused elements.

**Implementation Steps:**

1. Define KeyEvent trait and implementations
2. Implement `.on_key_down()` element method
3. Implement `.on_key_up()` element method
4. Route keyboard events only to focused element
5. Track modifier state (Ctrl, Shift, Alt, Cmd)

**Reference Files:**

- `zed/crates/gpui/src/input.rs` (KeyEvent types)
- Research doc section 3.1-3.2

**Acceptance Criteria:**

- [ ] KeyDownEvent reaches focused element only
- [ ] Modifier state tracked correctly
- [ ] Keystroke structure populated correctly
- [ ] Non-focused elements don't receive keyboard events

**Dependencies:** Task 1.4

---

### Phase 1 Deliverables

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

## Phase 2: Mouse Interactions (Weeks 3-4)

### Objectives

Implement comprehensive mouse interaction support including text selection, drag operations, hover effects, and scroll handling.

### Task 2.1: Drag Detection System

**Complexity:** Standard
**Files to Create:**

- `crates/pp-editor-events/src/mouse.rs` (expand)
- `crates/pp-editor-events/src/drag.rs`

**Description:**
Implement drag detection by tracking mouse-down followed by mouse-move events. Essential for text selection and drag-drop.

**Implementation Steps:**

1. Add `pressed_button: Option<MouseButton>` to window state
2. Set pressed_button on mouse-down
3. Clear pressed_button on mouse-up
4. Track `mouse_position: Point<Pixels>`
5. Detect drag: mouse-move while pressed_button is Some

**Reference Files:**

- reference codebase audit section 2.4
- `zed/crates/gpui/src/window.rs` (WindowState structure)

**Acceptance Criteria:**

- [ ] Drag detected when moving with button pressed
- [ ] Drag not triggered on stationary press
- [ ] Button identity preserved during drag
- [ ] Drag state cleared on mouse-up

**Dependencies:** Task 1.5

---

### Task 2.2: PositionMap Integration for Text Coordinates

**Complexity:** Standard
**Files to Create:**

- `crates/pp-editor-events/src/position_map.rs`

**Description:**
Integrate or create PositionMap for converting pixel coordinates to buffer positions. Required for accurate text selection.

**Implementation Steps:**

1. Review DisplayMap ADR for PositionMap interface
2. Create stub PositionMap if DisplayMap not ready
3. Implement `position_from_point(Point<Pixels>)` method
4. Implement `bounds_for_position(Position)` method
5. Cache position lookups for performance

**Reference Files:**

- [[2026-02-04-adopt-zed-displaymap]]
- `zed/crates/editor/src/element.rs` (position_map usage)
- Research doc section 2.3

**Acceptance Criteria:**

- [ ] Pixel to buffer position conversion works
- [ ] Handles multi-byte characters correctly
- [ ] Works with wrapped lines (future-proof)
- [ ] Performance < 1ms for typical clicks

**Dependencies:** Task 2.1 (conceptually also DisplayMap, but can stub)

---

### Task 2.3: Text Selection with Mouse Drag

**Complexity:** Complex
**Files to Create:**

- `crates/pp-editor-events/src/selection.rs`
- `crates/pp-editor-events/tests/selection_tests.rs`

**Description:**
Implement text selection by dragging mouse across text. Updates selection range continuously during drag.

**Implementation Steps:**

1. On mouse-down: set selection anchor to clicked position
2. On mouse-move (if dragging): update selection end to current position
3. On mouse-up: finalize selection
4. Handle selection direction (forward/backward)
5. Render selection highlighting during drag

**Reference Files:**

- reference codebase audit section 6.2
- `zed/crates/editor/src/element.rs` (lines 800-1200)
- ADR appendix example 3

**Acceptance Criteria:**

- [ ] Click-drag selects text
- [ ] Selection updates smoothly during drag
- [ ] Selection direction handled correctly
- [ ] Selection persists after mouse-up

**Dependencies:** Task 2.1, Task 2.2

---

### Task 2.4: Shift-Click Range Selection

**Complexity:** Standard
**Files to Create:**

- `crates/pp-editor-events/src/selection.rs` (expand)

**Description:**
Implement shift-click to extend selection from current cursor position to clicked position.

**Implementation Steps:**

1. Detect shift modifier in mouse-down event
2. Keep existing selection anchor
3. Extend selection end to clicked position
4. Maintain selection direction
5. Handle multiple shift-clicks

**Reference Files:**

- Research doc section 2.3
- `zed/crates/editor/src/element.rs` (shift-click logic)

**Acceptance Criteria:**

- [ ] Shift-click extends from cursor
- [ ] Works in both forward and backward directions
- [ ] Multiple shift-clicks update correctly
- [ ] Non-shift click resets selection

**Dependencies:** Task 2.3

---

### Task 2.5: Hover State Management

**Complexity:** Simple
**Files to Create:**

- `crates/pp-editor-events/src/hover.rs`
- `crates/pp-editor-events/tests/hover_tests.rs`

**Description:**
Implement hover event tracking and state management. Elements can respond to mouse entering/leaving.

**Implementation Steps:**

1. Track `hovered_hitbox: Option<HitboxId>` in window state
2. Compare current hit test with previous on mouse-move
3. Fire `on_mouse_exit` when leaving element
4. Fire `on_hover` when entering element
5. Implement `.on_hover()` element method

**Reference Files:**

- Research doc section 2.4
- GitHub Issue #12474 (known hover behavior quirk)

**Acceptance Criteria:**

- [ ] Hover state updates on mouse-move
- [ ] Mouse exit event fires when leaving
- [ ] Hover event fires when entering
- [ ] State management doesn't leak memory

**Dependencies:** Task 1.3 (hit testing)

---

### Task 2.6: Cursor Style Management

**Complexity:** Simple
**Files to Create:**

- `crates/pp-editor-events/src/cursor.rs`

**Description:**
Implement cursor style changes based on element context. Different cursors for text areas, buttons, resize handles, etc.

**Implementation Steps:**

1. Define CursorStyle enum (IBeam, Arrow, PointingHand, etc.)
2. Implement `.cursor(CursorStyle)` element method
3. Track cursor style per hitbox
4. Apply cursor from front-most hitbox under mouse
5. Platform-specific cursor loading

**Reference Files:**

- Research doc section 2.6
- GPUI CursorStyle enum

**Acceptance Criteria:**

- [ ] IBeam cursor over text areas
- [ ] Arrow cursor over general UI
- [ ] PointingHand over clickable elements
- [ ] Cursor changes immediately on hover

**Dependencies:** Task 2.5

---

### Task 2.7: Scroll Event Handling

**Complexity:** Standard
**Files to Create:**

- `crates/pp-editor-events/src/scroll.rs`
- `crates/pp-editor-events/tests/scroll_tests.rs`

**Description:**
Implement scroll wheel event handling with pixel vs line scroll detection. Update viewport position on scroll.

**Implementation Steps:**

1. Handle ScrollWheelEvent from platform
2. Detect precise pixel scrolling vs line scrolling
3. Implement `.on_scroll()` element method
4. Route scroll events through hit testing
5. Handle horizontal vs vertical scrolling

**Reference Files:**

- `zed/crates/gpui/src/input.rs` (ScrollWheelEvent)
- reference codebase audit section 2.3 (HitboxBehavior for scroll)

**Acceptance Criteria:**

- [ ] Scroll events update viewport
- [ ] Precise scrolling feels smooth
- [ ] Line scrolling works correctly
- [ ] Horizontal scrolling functional

**Dependencies:** Task 1.3 (hit testing)

---

### Phase 2 Deliverables

**Mouse Interactions:**

- [ ] Drag detection operational
- [ ] Text selection with mouse drag
- [ ] Shift-click range selection
- [ ] Hover effects working
- [ ] Cursor style changes
- [ ] Scroll event handling

**Testing:**

- [ ] Unit tests for drag detection
- [ ] Unit tests for position mapping
- [ ] Integration test: select text with mouse
- [ ] Integration test: shift-click extends selection
- [ ] Manual testing: hover and cursor changes

**Documentation:**

- [ ] Mouse interaction patterns documented
- [ ] Text selection API documented
- [ ] Cursor style usage guide

---

## Phase 3: Keyboard and Actions (Weeks 5-6)

### Objectives

Implement GPUI's action system for semantic commands, configure keybindings, and add multi-stroke keystroke support.

### Task 3.1: Action System Foundation

**Complexity:** Standard
**Files to Create:**

- `crates/pp-editor-events/src/actions.rs`
- `crates/pp-editor-events/src/dispatch.rs`

**Description:**
Implement GPUI's action trait and registration system. Actions decouple intent from input method.

**Implementation Steps:**

1. Define core editor actions (MoveCursor, DeleteLine, Copy, Paste, etc.)
2. Use `#[gpui::action]` attribute for action types
3. Implement action registration in dispatch tree
4. Create action handler registration API (`.on_action()`)
5. Implement action dispatch through dispatch tree

**Reference Files:**

- `zed/crates/gpui/src/key_dispatch.rs`
- Research doc section 3.3
- ADR appendix example 2

**Acceptance Criteria:**

- [ ] Actions defined with #[gpui::action]
- [ ] Action handlers register correctly
- [ ] Action dispatch reaches handlers
- [ ] Type-safe action system operational

**Dependencies:** Task 1.4 (focus management)

---

### Task 3.2: KeyContext and Context Predicates

**Complexity:** Standard
**Files to Create:**

- `crates/pp-editor-events/src/key_context.rs`
- `crates/pp-editor-events/tests/context_tests.rs`

**Description:**
Implement KeyContext stack for context-aware action dispatch. Allows different keybindings in different UI contexts.

**Implementation Steps:**

1. Define KeyContext struct with SmallVec storage
2. Implement `.key_context("editor")` element method
3. Build context stack during dispatch tree construction
4. Match actions against context predicates
5. Implement context priority resolution

**Reference Files:**

- reference codebase audit section 3.3
- `zed/crates/gpui/src/key_dispatch.rs` (KeyContext)

**Acceptance Criteria:**

- [ ] Context stack builds correctly
- [ ] Context predicates filter actions
- [ ] Child contexts override parent contexts
- [ ] Context matching efficient (< 1ms)

**Dependencies:** Task 3.1

---

### Task 3.3: Keymap Configuration System

**Complexity:** Standard
**Files to Create:**

- `crates/pp-editor-events/src/keymap.rs`
- `crates/pp-editor-events/src/keymap_parser.rs`
- `crates/pp-editor-events/tests/keymap_tests.rs`
- `config/keymap.toml` (example configuration)

**Description:**
Implement keymap configuration loading from TOML files. Binds keystrokes to actions without code changes.

**Implementation Steps:**

1. Define keymap TOML schema
2. Implement keymap parser (use serde)
3. Load keymap at application startup
4. Register keybindings in dispatch tree
5. Support multiple keymaps (user, default)

**Reference Files:**

- `zed/crates/gpui/src/keymap.rs`
- Research doc section 3.3

**Keymap Schema Example:**

```toml
[[bindings]]
context = "editor"
keystroke = "ctrl-s"
action = "workspace::Save"

[[bindings]]
context = "editor"
keystroke = "ctrl-k ctrl-d"
action = "editor::DeleteLine"
```

**Acceptance Criteria:**

- [ ] Keymap loads from TOML
- [ ] Single-keystroke bindings work
- [ ] Multi-stroke bindings work
- [ ] Context filtering applies correctly

**Dependencies:** Task 3.2

---

### Task 3.4: Multi-Stroke Keystroke Accumulation

**Complexity:** Standard
**Files to Create:**

- `crates/pp-editor-events/src/keystroke_matcher.rs`
- `crates/pp-editor-events/tests/keystroke_tests.rs`

**Description:**
Implement keystroke accumulation for multi-stroke keybindings (e.g., Ctrl+K Ctrl+D) with timeout handling.

**Implementation Steps:**

1. Create KeystrokeMatcher struct with pending keystrokes
2. Implement 1-second timeout (KEYSTROKE_TIMEOUT constant)
3. Accumulate keystrokes on key-down
4. Match against registered multi-stroke bindings
5. Clear pending keystrokes on timeout

**Reference Files:**

- reference codebase audit section 3.2
- `zed/crates/gpui/src/key_dispatch.rs` (KeystrokeMatcher)

**Acceptance Criteria:**

- [ ] Multi-stroke sequences accumulate
- [ ] Timeout clears pending keystrokes
- [ ] Partial matches return PendingMatch
- [ ] Complete matches return MatchedAction

**Dependencies:** Task 3.3

---

### Task 3.5: Keystroke Timeout Handling

**Complexity:** Standard
**Files to Create:**

- `crates/pp-editor-events/src/keystroke_matcher.rs` (expand)

**Description:**
Implement timeout behavior for multi-stroke sequences. After 1 second without continuation, clear pending keystrokes.

**Implementation Steps:**

1. Track timestamp of last keystroke
2. Compare current time with last keystroke time
3. Clear pending keystrokes if > 1 second elapsed
4. Optionally show pending keystroke indicator in UI
5. Handle timeout during keystroke accumulation

**Reference Files:**

- reference codebase audit section 3.2
- Research doc section 3.2

**Acceptance Criteria:**

- [ ] 1-second timeout enforced
- [ ] Pending keystrokes cleared on timeout
- [ ] UI indication of pending state (optional)
- [ ] Timeout doesn't interfere with fast typing

**Dependencies:** Task 3.4

---

### Task 3.6: Unmatched Keystroke Replay

**Complexity:** Simple
**Files to Create:**

- `crates/pp-editor-events/src/keystroke_matcher.rs` (expand)

**Description:**
Convert unmatched keystroke sequences to text input. Allows typing characters even if they partially match keybindings.

**Implementation Steps:**

1. Detect when keystroke sequence has no possible matches
2. Convert pending keystrokes to character input
3. Insert characters into text buffer
4. Clear pending keystrokes after replay
5. Handle modifier keys (don't replay Ctrl+X as 'x')

**Reference Files:**

- reference codebase audit section 3.5
- Research doc section 3.3

**Acceptance Criteria:**

- [ ] Unmatched keystrokes become text
- [ ] Modifier-only strokes don't replay
- [ ] Character order preserved
- [ ] No duplicate text insertion

**Dependencies:** Task 3.5

---

### Phase 3 Deliverables

**Action System:**

- [ ] Action trait and registration
- [ ] KeyContext stack functional
- [ ] Keymap configuration loading
- [ ] Multi-stroke keystroke support
- [ ] Keystroke timeout handling
- [ ] Unmatched keystroke replay

**Testing:**

- [ ] Unit tests for action dispatch
- [ ] Unit tests for context matching
- [ ] Unit tests for keystroke accumulation
- [ ] Integration test: keybinding triggers action
- [ ] Integration test: multi-stroke sequence works

**Documentation:**

- [ ] Action system architecture
- [ ] Keymap configuration guide
- [ ] Creating custom actions
- [ ] Context filtering patterns

---

## Phase 4: Focus and Navigation (Week 7)

### Objectives

Complete focus management implementation with tab navigation, focus visual indicators, and programmatic focus control.

### Task 4.1: Tab Order Configuration

**Complexity:** Simple
**Files to Create:**

- `crates/pp-editor-events/src/tab_order.rs`
- `crates/pp-editor-events/tests/tab_order_tests.rs`

**Description:**
Implement tab order configuration for keyboard navigation. Elements can specify tab index for custom ordering.

**Implementation Steps:**

1. Add `tab_index: Option<i32>` to focusable elements
2. Implement `.tab_index(i32)` element method
3. Sort focusable elements by tab index during dispatch tree construction
4. Default tab order: visual order (top-to-bottom, left-to-right)
5. Implement `.tab_stop(bool)` to exclude elements

**Reference Files:**

- Research doc section 4.2

**Acceptance Criteria:**

- [ ] Tab index ordering works
- [ ] Default visual order correct
- [ ] Negative tab indices work (focus last)
- [ ] tab_stop(false) excludes elements

**Dependencies:** Task 1.4

---

### Task 4.2: Tab Key Navigation

**Complexity:** Standard
**Files to Create:**

- `crates/pp-editor-events/src/tab_navigation.rs`
- `crates/pp-editor-events/tests/tab_navigation_tests.rs`

**Description:**
Implement tab key navigation to cycle through focusable elements. Shift+Tab reverses direction.

**Implementation Steps:**

1. Register Tab action for tab key
2. Register ReverseTab action for shift-tab
3. Find next focusable element in tab order
4. Transfer focus to next element
5. Handle wrap-around (last -> first)

**Reference Files:**

- Research doc section 4.2-4.3

**Acceptance Criteria:**

- [ ] Tab moves focus forward
- [ ] Shift-Tab moves focus backward
- [ ] Focus wraps around at boundaries
- [ ] Skips tab_stop(false) elements

**Dependencies:** Task 4.1

---

### Task 4.3: Focus Visual Indicators

**Complexity:** Simple
**Files to Create:**

- `crates/pp-editor-events/src/focus_visual.rs`

**Description:**
Implement visual feedback for focused elements. Typically rendered as border or background color change.

**Implementation Steps:**

1. Check focus state in element render method
2. Apply focused styling when element focused
3. Use `.when(self.focus_handle.is_focused(cx), |el| {...})`
4. Implement focus ring/border styling
5. Support theming for focus colors

**Reference Files:**

- Research doc section 4.2

**Acceptance Criteria:**

- [ ] Focused element visually distinct
- [ ] Focus indicator appears immediately
- [ ] Focus indicator clears on blur
- [ ] Accessible focus indication (WCAG compliant)

**Dependencies:** Task 4.2

---

### Task 4.4: Focus Event Propagation

**Complexity:** Simple
**Files to Create:**

- `crates/pp-editor-events/src/focus.rs` (expand)

**Description:**
Implement focus and blur events that fire when element gains/loses focus.

**Implementation Steps:**

1. Define FocusEvent and BlurEvent types
2. Implement `.on_focus()` element method
3. Implement `.on_blur()` element method
4. Fire events during focus transfer
5. Propagate events through dispatch tree

**Reference Files:**

- GPUI focus system

**Acceptance Criteria:**

- [ ] Focus event fires on focus gain
- [ ] Blur event fires on focus loss
- [ ] Events fire in correct order (blur then focus)
- [ ] Event handlers receive focus change details

**Dependencies:** Task 4.2

---

### Task 4.5: Parent Focus Awareness

**Complexity:** Simple
**Files to Create:**

- `crates/pp-editor-events/src/focus.rs` (expand)

**Description:**
Implement `.contains_focused()` method for parents to detect child focus state. Useful for container styling.

**Implementation Steps:**

1. Implement `contains_focused(cx)` method
2. Check if any descendant has focus
3. Use for conditional styling in parent elements
4. Optimize check to avoid traversing entire tree
5. Cache contains_focused result per frame

**Reference Files:**

- Research doc section 4.2

**Acceptance Criteria:**

- [ ] Correctly detects child focus
- [ ] Updates when child focus changes
- [ ] Performance acceptable (< 0.1ms)
- [ ] Works with nested containers

**Dependencies:** Task 4.4

---

### Task 4.6: Programmatic Focus Changes

**Complexity:** Simple
**Files to Create:**

- `crates/pp-editor-events/src/focus.rs` (expand)

**Description:**
Implement programmatic focus control via `cx.focus(&focus_handle)`. Allows code to change focus explicitly.

**Implementation Steps:**

1. Implement `cx.focus(&focus_handle)` method
2. Blur currently focused element
3. Focus target element
4. Fire blur and focus events
5. Update dispatch tree focus tracking

**Reference Files:**

- GPUI focus system

**Acceptance Criteria:**

- [ ] cx.focus() transfers focus
- [ ] Focus and blur events fire
- [ ] Focus visual indicator updates
- [ ] Works from any context (event handlers, timers, etc.)

**Dependencies:** Task 4.4

---

### Phase 4 Deliverables

**Focus Management:**

- [ ] Tab order configuration
- [ ] Tab key navigation (forward and reverse)
- [ ] Focus visual indicators
- [ ] Focus and blur events
- [ ] Parent focus awareness
- [ ] Programmatic focus control

**Testing:**

- [ ] Unit tests for tab order
- [ ] Integration test: tab navigation cycles focus
- [ ] Integration test: focus visuals appear
- [ ] Manual test: keyboard navigation functional

**Documentation:**

- [ ] Focus management guide
- [ ] Tab navigation patterns
- [ ] Focus styling guide
- [ ] Accessibility considerations

---

## Phase 5: IME Support (Week 8)

### Objectives

Implement PlatformInputHandler for native IME support, enabling composition for CJK languages and complex input methods.

### Task 5.1: PlatformInputHandler Trait Implementation

**Complexity:** Complex
**Files to Create:**

- `crates/pp-editor-events/src/ime.rs`
- `crates/pp-editor-events/src/ime/handler.rs`
- `crates/pp-editor-events/tests/ime_tests.rs`

**Description:**
Implement GPUI's PlatformInputHandler trait to bridge editor with native platform IME systems.

**Implementation Steps:**

1. Implement `text_for_range(range)` - return text in range
2. Implement `selected_text_range(ignore_disabled)` - return selection
3. Implement `marked_text_range()` - return composition range
4. Implement `unmark_text()` - clear composition
5. Implement `replace_text_in_range(range, text)` - simple text replacement
6. Implement `replace_and_mark_text_in_range(range, text, new_range)` - composition
7. Implement `bounds_for_range(range)` - position candidate window
8. Implement `supports_character_insertion()` - return true

**Reference Files:**

- reference codebase audit section 4.1
- `zed/crates/gpui/src/platform.rs` (InputHandler trait)
- `zed/crates/gpui/src/element_input_handler.rs`
- ADR appendix example 4

**Acceptance Criteria:**

- [ ] All trait methods implemented
- [ ] Compiles without errors
- [ ] Basic text input works (ASCII)
- [ ] Selection tracking functional

**Dependencies:** Task 2.2 (PositionMap for bounds)

---

### Task 5.2: Composition Range Tracking

**Complexity:** Standard
**Files to Create:**

- `crates/pp-editor-events/src/ime/composition.rs`

**Description:**
Track composition state during IME input. Composition is the temporary text before user commits final characters.

**Implementation Steps:**

1. Add `composition_range: Option<Range<usize>>` to editor state
2. Set composition_range in `replace_and_mark_text_in_range()`
3. Clear composition_range in `unmark_text()`
4. Render composition text with distinct styling
5. Handle composition cancellation (ESC key)

**Reference Files:**

- Research doc section 5.1-5.2

**Acceptance Criteria:**

- [ ] Composition range tracked correctly
- [ ] Composition text visually distinct
- [ ] Composition clears on commit
- [ ] Composition cancellation works

**Dependencies:** Task 5.1

---

### Task 5.3: Candidate Window Positioning

**Complexity:** Standard
**Files to Create:**

- `crates/pp-editor-events/src/ime/candidate.rs`

**Description:**
Implement `bounds_for_range()` to position IME candidate selection window near cursor.

**Implementation Steps:**

1. Use PositionMap to get pixel bounds for text range
2. Convert bounds to screen coordinates
3. Account for viewport scrolling
4. Return bounds that position candidate window below cursor
5. Handle edge cases (near window edge)

**Reference Files:**

- reference codebase audit section 4.1
- Research doc section 5.1

**Acceptance Criteria:**

- [ ] Candidate window appears near cursor
- [ ] Bounds calculation correct for all positions
- [ ] Works with scrolled viewport
- [ ] Handles window edge cases

**Dependencies:** Task 5.1, Task 2.2

---

### Task 5.4: Marked Text Rendering

**Complexity:** Standard
**Files to Create:**

- `crates/pp-editor-events/src/ime/rendering.rs`

**Description:**
Render composition text with special styling (typically underline or different color) to distinguish from committed text.

**Implementation Steps:**

1. Query `marked_text_range()` during text rendering
2. Apply composition styling to marked text
3. Support platform-specific composition styles
4. Render composition text underline
5. Handle composition text selection

**Reference Files:**

- reference codebase audit section 4.2

**Acceptance Criteria:**

- [ ] Composition text visually distinct
- [ ] Underline renders correctly
- [ ] Composition text selectable
- [ ] Style clears on commit

**Dependencies:** Task 5.2

---

### Task 5.5: Text Replacement with Composition

**Complexity:** Standard
**Files to Create:**

- `crates/pp-editor-events/src/ime/replacement.rs`

**Description:**
Implement text replacement during composition. As user types, composition text updates continuously.

**Implementation Steps:**

1. Handle `replace_and_mark_text_in_range()` calls
2. Replace text in specified range
3. Update composition range
4. Update cursor/selection
5. Trigger re-render

**Reference Files:**

- ADR appendix example 4
- Research doc section 5.3

**Acceptance Criteria:**

- [ ] Composition text updates continuously
- [ ] Text replacement atomic (no partial states)
- [ ] Undo/redo handles composition correctly
- [ ] Performance acceptable during rapid input

**Dependencies:** Task 5.2

---

### Task 5.6: Cross-Platform IME Testing

**Complexity:** Standard
**Files to Create:**

- `crates/pp-editor-events/tests/ime_platform_tests.rs`
- `.docs/testing/ime-test-plan.md`

**Description:**
Test IME functionality across Windows, macOS, and Linux with various input methods.

**Testing Matrix:**

| Platform | Input Method | Language | Test Case |
|----------|--------------|----------|-----------|
| Windows | Microsoft IME | Japanese | Hiragana, Katakana, Kanji |
| Windows | Microsoft IME | Chinese | Pinyin input |
| macOS | Native | Japanese | Romaji to Kanji |
| macOS | Native | Chinese | Pinyin with tones |
| Linux | iBus | Japanese | Mozc input |
| Linux | Fcitx | Chinese | Simplified Chinese |

**Implementation Steps:**

1. Setup test input methods on each platform
2. Test Hiragana to Kanji conversion (Japanese)
3. Test Pinyin input with candidate selection (Chinese)
4. Test Hangul composition (Korean)
5. Test dead keys (European languages)
6. Document platform-specific quirks

**Reference Files:**

- Research doc section 5.2
- reference codebase audit section 5.3

**Acceptance Criteria:**

- [ ] Japanese input works on all platforms
- [ ] Chinese input works on all platforms
- [ ] Korean input works on all platforms
- [ ] Dead keys and combining characters work
- [ ] Documented known platform differences

**Dependencies:** Task 5.1-5.5

---

### Phase 5 Deliverables

**IME Support:**

- [ ] PlatformInputHandler implementation
- [ ] Composition state tracking
- [ ] Candidate window positioning
- [ ] Marked text rendering
- [ ] Text replacement during composition
- [ ] Cross-platform testing complete

**Testing:**

- [ ] Unit tests for IME state management
- [ ] Integration tests for composition flow
- [ ] Platform-specific tests passing
- [ ] Manual testing with real IMEs

**Documentation:**

- [ ] IME architecture documentation
- [ ] Platform-specific IME notes
- [ ] Testing guide for IME
- [ ] Known limitations documented

---

## Phase 6: Testing and Polish (Weeks 9-10)

### Objectives

Comprehensive testing, cross-platform validation, performance optimization, and documentation completion.

### Task 6.1: Hit Testing Unit Tests

**Complexity:** Simple
**Files to Create:**

- `crates/pp-editor-events/tests/hit_test_comprehensive.rs`

**Description:**
Comprehensive unit tests for hit testing logic covering all edge cases.

**Test Cases:**

1. Point inside single hitbox
2. Point outside all hitboxes
3. Overlapping hitboxes (front-to-back order)
4. Content mask clipping
5. HitboxBehavior filtering (BlockMouse, BlockMouseExceptScroll)
6. Nested hitboxes
7. Zero-size hitboxes (should not match)
8. Negative coordinate hitboxes

**Acceptance Criteria:**

- [ ] All test cases pass
- [ ] Code coverage > 95% for hit testing module
- [ ] Edge cases documented
- [ ] Performance benchmarks included

**Dependencies:** Task 1.3

---

### Task 6.2: Event Propagation Integration Tests

**Complexity:** Standard
**Files to Create:**

- `crates/pp-editor-events/tests/integration/propagation.rs`

**Description:**
Test complete event flow from platform input to handler execution across both capture and bubble phases.

**Test Scenarios:**

1. Click event reaches correct element
2. Capture phase handlers execute before bubble
3. StopPropagation prevents further dispatch
4. Keyboard events only reach focused element
5. Mouse events reach all elements under cursor
6. Scroll events respect HitboxBehavior
7. Parent handlers execute after child handlers
8. Action dispatch through correct context

**Acceptance Criteria:**

- [ ] All propagation scenarios tested
- [ ] Tests use only public APIs
- [ ] Tests run on all platforms
- [ ] Clear test failure messages

**Dependencies:** All previous tasks

---

### Task 6.3: Cross-Platform Testing Suite

**Complexity:** Standard
**Files to Create:**

- `crates/pp-editor-events/tests/platform/windows.rs`
- `crates/pp-editor-events/tests/platform/macos.rs`
- `crates/pp-editor-events/tests/platform/linux.rs`
- `.github/workflows/test-event-handling.yml`

**Description:**
Platform-specific integration tests validating consistent behavior across Windows, macOS, and Linux.

**Platform Test Coverage:**

**Windows:**

- [ ] WM_LBUTTONDOWN → MouseDownEvent
- [ ] WM_KEYDOWN with modifiers
- [ ] WM_IME_COMPOSITION handling
- [ ] Dead key sequences

**macOS:**

- [ ] NSEvent → PlatformInput conversion
- [ ] Precise scroll delta detection
- [ ] Command key vs Ctrl key
- [ ] Native IME integration

**Linux:**

- [ ] Wayland pointer events
- [ ] X11 input handling
- [ ] IBus/Fcitx compatibility
- [ ] Multiple desktop environments

**Implementation:**

1. Setup CI runners for each platform
2. Write platform-specific tests
3. Mock platform events where possible
4. Test event field correctness
5. Validate modifier key handling

**Acceptance Criteria:**

- [ ] Tests pass on Windows
- [ ] Tests pass on macOS
- [ ] Tests pass on Linux
- [ ] CI runs tests automatically
- [ ] Platform differences documented

**Dependencies:** All previous tasks

---

### Task 6.4: Performance Benchmarks

**Complexity:** Standard
**Files to Create:**

- `crates/pp-editor-events/benches/event_handling.rs`
- `crates/pp-editor-events/benches/hit_testing.rs`
- `.docs/performance/event-benchmarks.md`

**Description:**
Performance benchmarks for critical event handling paths to ensure 60 FPS target.

**Benchmark Targets:**

| Operation | Target Latency |
|-----------|----------------|
| Hit testing (10 hitboxes) | < 0.1ms |
| Hit testing (100 hitboxes) | < 1ms |
| Mouse event dispatch | < 1ms |
| Keyboard event dispatch | < 1ms |
| Action matching | < 0.5ms |
| Context predicate evaluation | < 0.1ms |
| Focus transfer | < 0.5ms |
| **Total event handling** | **< 16ms (60 FPS)** |

**Implementation:**

1. Use `criterion` crate for benchmarks
2. Benchmark hit testing with varying hitbox counts
3. Benchmark action matching with complex keymaps
4. Benchmark focus transfer
5. Create synthetic event load tests (1000 events/sec)

**Acceptance Criteria:**

- [ ] All benchmarks meet target latencies
- [ ] Benchmarks run in CI
- [ ] Performance regression detection
- [ ] Optimization opportunities identified

**Dependencies:** All previous tasks

---

### Task 6.5: Event System Documentation

**Complexity:** Standard
**Files to Create:**

- `.docs/architecture/event-system.md`
- `.docs/guides/handling-mouse-events.md`
- `.docs/guides/handling-keyboard-events.md`
- `.docs/guides/creating-actions.md`
- `.docs/guides/implementing-ime.md`
- `.docs/api/event-handler-reference.md`

**Description:**
Comprehensive documentation of event system architecture, patterns, and API usage.

**Documentation Structure:**

**Architecture Document:**

- System overview
- Two-phase dispatch explanation
- Hitbox system
- Dispatch tree
- Focus management
- IME integration

**Pattern Guides:**

- When to use direct handlers vs actions
- Implementing mouse interactions
- Implementing keyboard commands
- Managing focus
- Supporting IME

**API Reference:**

- All public types documented
- Code examples for common patterns
- Decision flowcharts
- Troubleshooting guide

**Acceptance Criteria:**

- [ ] All public APIs documented
- [ ] Architecture diagrams included
- [ ] Code examples compile and run
- [ ] Reviewed for clarity

**Dependencies:** All previous tasks

---

### Task 6.6: Example Implementations

**Complexity:** Simple
**Files to Create:**

- `examples/basic_button.rs`
- `examples/text_input.rs`
- `examples/tab_navigation.rs`
- `examples/ime_composition.rs`
- `examples/custom_actions.rs`

**Description:**
Working example implementations demonstrating common event handling patterns.

**Examples:**

1. **Basic Button**: Click handler, hover effect, cursor change
2. **Text Input**: Keyboard input, selection, composition
3. **Tab Navigation**: Multiple focusable elements, tab order
4. **IME Composition**: Japanese/Chinese input
5. **Custom Actions**: Define action, register handler, configure keybinding

**Acceptance Criteria:**

- [ ] All examples compile and run
- [ ] Examples demonstrate best practices
- [ ] Examples include comments
- [ ] Examples referenced in documentation

**Dependencies:** All previous tasks

---

### Phase 6 Deliverables

**Testing:**

- [ ] Unit test coverage > 80%
- [ ] Integration tests for all critical paths
- [ ] Cross-platform test suite passing
- [ ] Performance benchmarks meeting targets

**Documentation:**

- [ ] Architecture documentation complete
- [ ] Pattern guides published
- [ ] API reference complete
- [ ] Example implementations provided

**Quality:**

- [ ] No compiler warnings
- [ ] No clippy warnings
- [ ] All acceptance criteria met
- [ ] Code reviewed and approved

---

## Implementation Guidelines

### Code Standards

**Rust Edition and Version:**

- Use Rust Edition 2024
- Minimum rust-version = "1.93"

**Visibility:**

- Default to `pub(crate)` for internal APIs
- Use `pub` only for true public APIs
- Use `pub(super)` for parent module access

**Safety:**

- `#![forbid(unsafe_code)]` in all event handling crates
- No unsafe blocks without explicit justification

**Dependencies:**

```toml
[dependencies]
gpui = { path = "../gpui" }
smallvec = "1.11"  # For KeyContext storage
serde = { version = "1.0", features = ["derive"] }  # For keymap parsing
```

### Testing Standards

**Unit Tests:**

- Located in `#[cfg(test)] mod tests` within implementation files
- Test only public APIs
- Use descriptive test names (test_<behavior>_<condition>)

**Integration Tests:**

- Located in `tests/` directory
- Test only public APIs
- Cross-platform when possible

**Snapshot Testing:**

- Use `insta` crate for snapshot tests where applicable
- Useful for keymap parsing, action dispatch results

### Documentation Standards

**Public API Documentation:**

- All public types, traits, functions documented
- Include usage examples in doc comments
- Document safety requirements and invariants
- Link related types and functions

**Internal Documentation:**

- Complex algorithms have explanation comments
- Non-obvious design decisions documented
- Reference source files where applicable

### File Organization

**Crate Structure:**

```
crates/pp-editor-events/
├── Cargo.toml
├── src/
│   ├── lib.rs              # Public API exports
│   ├── window.rs           # Window and event loop
│   ├── hitbox.rs           # Hitbox types
│   ├── hit_test.rs         # Hit testing algorithm
│   ├── mouse.rs            # Mouse event handlers
│   ├── keyboard.rs         # Keyboard event handlers
│   ├── focus.rs            # Focus management
│   ├── actions.rs          # Action system
│   ├── key_context.rs      # KeyContext implementation
│   ├── keymap.rs           # Keymap configuration
│   ├── keystroke_matcher.rs # Multi-stroke handling
│   ├── ime.rs              # IME coordination
│   ├── ime/
│   │   ├── handler.rs      # PlatformInputHandler impl
│   │   ├── composition.rs  # Composition state
│   │   ├── candidate.rs    # Candidate positioning
│   │   └── rendering.rs    # Marked text rendering
│   └── dispatch.rs         # Event dispatch logic
├── tests/
│   ├── hit_test_tests.rs
│   ├── mouse_tests.rs
│   ├── keyboard_tests.rs
│   ├── focus_tests.rs
│   ├── actions_tests.rs
│   └── ime_tests.rs
├── benches/
│   ├── event_handling.rs
│   └── hit_testing.rs
└── examples/
    ├── basic_button.rs
    ├── text_input.rs
    └── ime_composition.rs
```

---

## Task Execution Workflow

### For Sub-Agent Execution

Each task is designed for execution by a single sub-agent (via `.agent/scripts/acp_dispatch.py`). Tasks are granular, focused, and include clear acceptance criteria.

**Task Document Format for Sub-Agent:**

```markdown
# Task: [Task Name]

## Context
- Phase: [Phase Number]
- Complexity: [Simple/Standard/Complex]
- Estimated Time: [X hours/days]

## Objective
[Clear statement of what this task achieves]

## Dependencies
[List of task IDs that must complete first]

## Reference Files
[Reference source files to consult as implementation guides]

## Implementation Steps
1. [Concrete step 1]
2. [Concrete step 2]
...

## Acceptance Criteria
- [ ] Criterion 1
- [ ] Criterion 2
...

## Testing Requirements
[Specific tests to write]

## Files to Create/Modify
[List of file paths]
```

### Sequential vs Parallel Execution

**Sequential Tasks:**
Tasks with dependencies must execute sequentially. Example:

- Task 1.1 → Task 1.2 → Task 1.3 (hit testing depends on hitbox system)

**Parallel Tasks:**
Independent tasks within a phase can execute in parallel:

- Task 2.5 (hover) and Task 2.6 (cursor) are independent
- Task 3.1 (actions) and Task 3.2 (context) can start together

### Progress Tracking

Track completion in `.docs/exec/2026-02-04-editor-event-handling/`:

- `phase-1-progress.md`
- `phase-2-progress.md`
- ...
- `summary.md` (overall status)

---

## Risk Management

### High-Risk Areas

**1. IME Implementation (Phase 5)**

- **Risk:** Platform-specific behavior differences
- **Mitigation:** Extensive testing on all platforms, early prototype
- **Contingency:** Document limitations, plan future improvements

**2. Performance (Phase 6)**

- **Risk:** Event handling latency exceeds 16ms target
- **Mitigation:** Continuous benchmarking, optimization passes
- **Contingency:** Identify bottlenecks, optimize critical paths

**3. Cross-Platform Consistency (All Phases)**

- **Risk:** Behavior differs between platforms
- **Mitigation:** Platform-specific testing throughout, GPUI abstractions
- **Contingency:** Document platform differences, provide fallbacks

**4. GPUI Documentation Gaps (All Phases)**

- **Risk:** Insufficient documentation for GPUI features
- **Mitigation:** Use reference codebase source as guide, engage community
- **Contingency:** Study GPUI source code directly, ask in the GPUI community

### Medium-Risk Areas

**1. Multi-Stroke Keybindings (Phase 3)**

- **Risk:** Complex timeout and replay logic
- **Mitigation:** Comprehensive unit tests, reference implementation
- **Contingency:** Simplify to single-stroke only initially

**2. Hit Testing Performance (Phase 1-2)**

- **Risk:** Slow hit testing with many hitboxes
- **Mitigation:** Early benchmarking, efficient algorithms
- **Contingency:** Spatial indexing (quadtree) if needed

**3. Focus Management Complexity (Phase 4)**

- **Risk:** Focus state synchronization issues
- **Mitigation:** Clear state ownership, thorough testing
- **Contingency:** Simplify focus model, rely on GPUI primitives

---

## Success Metrics

### Functional Metrics

**Phase 1 Success:**

- [ ] Window receives platform events
- [ ] Click reaches correct element
- [ ] Keyboard events reach focused element

**Phase 2 Success:**

- [ ] Text selection with mouse drag works smoothly
- [ ] Hover effects responsive
- [ ] Scrolling updates viewport

**Phase 3 Success:**

- [ ] Keybindings trigger actions
- [ ] Multi-stroke sequences work
- [ ] Custom keymaps load correctly

**Phase 4 Success:**

- [ ] Tab navigation cycles focus
- [ ] Focus visually indicated
- [ ] Programmatic focus works

**Phase 5 Success:**

- [ ] Japanese input works
- [ ] Chinese input works
- [ ] Composition visually correct

**Phase 6 Success:**

- [ ] Test coverage > 80%
- [ ] Performance < 16ms
- [ ] Documentation complete

### Quality Metrics

**Code Quality:**

- [ ] No compiler warnings
- [ ] No clippy warnings with standard lints
- [ ] Consistent formatting (rustfmt)
- [ ] Public APIs documented

**Architecture Quality:**

- [ ] Clear separation: handlers vs actions
- [ ] Minimal code duplication
- [ ] Consistent patterns throughout
- [ ] Extensible design

**Test Quality:**

- [ ] Unit tests cover edge cases
- [ ] Integration tests validate full flows
- [ ] Platform-specific tests pass
- [ ] Manual testing checklist complete

---

## Appendix A: Task Dependency Graph

```
Phase 1: Core Infrastructure
1.1 Window Event Loop
  ├─→ 1.2 Hitbox Registration
  │     └─→ 1.3 Hit Testing
  │           └─→ 1.5 Click Handlers
  ├─→ 1.4 FocusHandle Foundation
        └─→ 1.6 Keyboard Handlers

Phase 2: Mouse Interactions
1.5 Click Handlers
  └─→ 2.1 Drag Detection
        └─→ 2.2 PositionMap Integration
              └─→ 2.3 Text Selection
                    └─→ 2.4 Shift-Click Selection

1.3 Hit Testing
  ├─→ 2.5 Hover Management
  │     └─→ 2.6 Cursor Styles
  └─→ 2.7 Scroll Handling

Phase 3: Keyboard and Actions
1.4 FocusHandle
  └─→ 3.1 Action System
        └─→ 3.2 KeyContext
              └─→ 3.3 Keymap Config
                    └─→ 3.4 Multi-Stroke Accumulation
                          └─→ 3.5 Timeout Handling
                                └─→ 3.6 Keystroke Replay

Phase 4: Focus and Navigation
3.1 Action System
  └─→ 4.1 Tab Order
        └─→ 4.2 Tab Navigation
              ├─→ 4.3 Focus Visuals
              ├─→ 4.4 Focus Events
              │     ├─→ 4.5 Parent Focus Awareness
              │     └─→ 4.6 Programmatic Focus

Phase 5: IME Support
2.2 PositionMap + 3.1 Action System
  └─→ 5.1 PlatformInputHandler
        ├─→ 5.2 Composition Tracking
        │     └─→ 5.4 Marked Text Rendering
        │           └─→ 5.5 Text Replacement
        ├─→ 5.3 Candidate Positioning
        └─→ 5.6 Cross-Platform Testing

Phase 6: Testing and Polish
All Previous Tasks
  ├─→ 6.1 Hit Testing Tests
  ├─→ 6.2 Propagation Tests
  ├─→ 6.3 Cross-Platform Tests
  ├─→ 6.4 Performance Benchmarks
  ├─→ 6.5 Documentation
  └─→ 6.6 Example Implementations
```

---

## Appendix B: Reference File Quick Lookup

### GPUI Core

| Topic | Reference File | Key Lines | Description |
|-------|----------|-----------|-------------|
| Event Types | `gpui/src/input.rs` | Full file | PlatformInput enum, MouseEvent, KeyEvent |
| Window Event Loop | `gpui/src/window.rs` | 1-500 | Window creation, event reception |
| Hit Testing | `gpui/src/window.rs` | 3976-4027 | Hitbox iteration, point containment |
| Hitbox Behaviors | `gpui/src/window.rs` | 842-864 | BlockMouse, BlockMouseExceptScroll |
| Action Dispatch | `gpui/src/window.rs` | 4029-4207 | Four-stage dispatch |
| Dispatch Tree | `gpui/src/key_dispatch.rs` | Full file | DispatchNode, KeystrokeMatcher |
| IME Interface | `gpui/src/platform.rs` | InputHandler trait | PlatformInputHandler methods |
| Focus System | `gpui/src/focus.rs` | Full file | FocusHandle, FocusId |

### Editor Implementation

| Topic | Reference File | Key Lines | Description |
|-------|----------|-----------|-------------|
| Editor Events | `editor/src/editor.rs` | Full file | Action handlers, cursor movement |
| Mouse Selection | `editor/src/element.rs` | 800-1200 | Click, drag, shift-click |
| IME Handler | `editor/src/element.rs` | IME sections | PlatformInputHandler impl |

### Examples

| Topic | Reference File | Description |
|-------|----------|-------------|
| Basic Input | `gpui/examples/input.rs` | Mouse and keyboard examples |

---

## Appendix C: Glossary

**Action:** A semantic command (e.g., DeleteLine, Save) that can be triggered by multiple input methods.

**Bubble Phase:** Event propagation from target element to root (front-to-back).

**Capture Phase:** Event propagation from root to target element (back-to-front).

**Composition:** Temporary text during IME input before final character commitment.

**Dispatch Tree:** Hierarchical structure representing UI element tree for event routing.

**FocusHandle:** Strong reference to focusable element for keyboard focus tracking.

**Hitbox:** Rectangular region that can receive mouse events.

**HitboxBehavior:** Controls how hitbox affects mouse event propagation (Normal, BlockMouse, BlockMouseExceptScroll).

**IME (Input Method Editor):** System for inputting complex characters (CJK languages).

**KeyContext:** String identifying UI context for keybinding filtering (e.g., "editor", "menu").

**Keystroke:** Key press with modifiers (e.g., Ctrl+K).

**Multi-Stroke Keybinding:** Keybinding requiring sequence of keystrokes (e.g., Ctrl+K Ctrl+D).

**PlatformInputHandler:** Trait for implementing IME support.

**PositionMap:** Data structure mapping pixel coordinates to text buffer positions.

**Two-Phase Dispatch:** Event propagation model with capture and bubble phases.

---

**Document Version:** 1.0
**Next Review:** After Phase 1 completion
**Execution Start Date:** [To be filled by executor]

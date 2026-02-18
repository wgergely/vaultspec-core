---
tags:
  - "#adr"
  - "#editor-event-handling"
date: 2026-02-04
related:
  - "[[2026-02-04-editor-event-handling]]"
  - "[[2026-02-04-editor-event-handling-plan]]"
  - "[[2026-02-04-adopt-zed-displaymap]]"
---

# ADR: Editor Event Handling Implementation

**Date:** 2026-02-04
**Status:** Accepted
**Deciders:** Lead Technical Researcher, Architecture Team

---

## Related Documents

- "[[2026-02-04-editor-event-handling|GPUI Event System Research]]"
- [[2026-02-04-editor-event-handling|Reference Codebase Audit]]
- [[2026-02-04-adopt-zed-displaymap|DisplayMap ADR]]
- [[2026-02-04-editor-text-layout|Text Layout Research]]

---

## Context

The popup-prompt editor requires a comprehensive event handling system to support:

1. **Mouse Interactions:** Click positioning, drag selection, hover effects, scroll events
2. **Keyboard Input:** Character insertion, command shortcuts, multi-stroke keybindings
3. **Focus Management:** Tab navigation, focus tracking, keyboard event routing
4. **IME Support:** Composition for CJK languages, candidate window positioning
5. **Cross-Platform Consistency:** Unified behavior across Windows, macOS, and Linux

### Current State

The project currently lacks a formalized event handling architecture. GPUI provides native event handling capabilities, but implementation patterns must be established.

### Research Findings

Investigation of both GPUI's event system (research document) and the reference editor's production implementation (audit document) revealed:

**GPUI Event System Strengths:**

- Two-phase dispatch model (capture + bubble) similar to DOM events
- Hitbox-based hit testing with content mask support
- Focus-aware dispatch tree for keyboard event routing
- Platform abstraction unifying Windows/macOS/Linux input
- Separation of key events from text input for IME support

**Reference Implementation Patterns:**

- Hybrid model: Direct event handlers for UI, actions for commands
- FocusHandle-based focus management with explicit tracking
- Multi-stroke keybinding support with 1-second timeout
- PlatformInputHandler trait for IME integration
- Coordinate transformation via PositionMap for text selection

**Key Technical Considerations:**

- GPUI forbids `unsafe` code, aligning with project standards
- Two-phase dispatch enables modal dismissal (capture) and normal handling (bubble)
- Action system decouples intent from input method, enabling rebindable keybindings
- IME requires separate text input handling from physical key events
- Platform-specific quirks require abstraction layer

### Architectural Options Considered

#### Option A: Direct Event Handlers Only

Use GPUI's low-level event handlers (`on_mouse_down`, `on_key_down`) for all event handling.

**Pros:**

- Minimal abstraction overhead
- Direct access to event data
- Full control over behavior
- Simple initial implementation

**Cons:**

- Extensive boilerplate for commands
- Manual focus management complexity
- No keybinding rebinding support
- Tight coupling of intent and input method

#### Option B: Action-Based System Only

Implement all interactions through GPUI's action system with semantic commands.

**Pros:**

- Rebindable keybindings out of the box
- Clean separation of intent and input
- Centralized command dispatch
- Excellent for keyboard commands

**Cons:**

- Overhead for simple UI interactions
- Indirect access to mouse event details
- Learning curve for action system
- Not ideal for hover/drag behaviors

#### Option C: Hybrid Model (Recommended)

Combine direct event handlers for UI-level interactions with action system for semantic commands.

**Pros:**

- Best of both approaches
- Actions for commands (save, delete line, move cursor)
- Direct handlers for UI (hover, click, drag)
- Proven architecture in reference codebase production code
- Flexible and maintainable

**Cons:**

- Two systems to understand
- Need clear guidelines for when to use each
- Slightly more complex architecture

---

## Decision

**Adopt GPUI's hybrid event handling model** combining:

1. **Direct Event Handlers** for UI-level mouse interactions:
   - `.on_mouse_down()` / `.on_mouse_up()` for click detection
   - `.on_mouse_move()` for drag operations and hover effects
   - `.on_scroll()` for scroll events
   - `.cursor()` for cursor style management

2. **Action System** for semantic keyboard commands:
   - `#[gpui::action]` attribute for command definitions
   - `.on_action()` for command handlers
   - Keymap configuration (JSON/TOML) for keybindings
   - Context-aware action dispatch

3. **Two-Phase Dispatch** for event propagation:
   - Capture phase (back→front): Modal dismissal, outside-click detection
   - Bubble phase (front→back): Normal event handling

4. **FocusHandle-Based** keyboard focus management:
   - `cx.new_focus_handle()` for focus tracking
   - `.track_focus(&focus_handle)` for element focus registration
   - Focus-aware keyboard event routing via dispatch tree

5. **PlatformInputHandler** for IME support:
   - `selected_text_range()` for selection tracking
   - `marked_text_range()` for composition state
   - `bounds_for_range()` for candidate window positioning
   - `replace_and_mark_text_in_range()` for composition text

### Rationale

This hybrid approach is justified by:

1. **Production Validation:** The reference editor successfully uses this architecture in production
2. **Separation of Concerns:** UI interactions distinct from semantic commands
3. **Flexibility:** Rebindable keybindings without sacrificing low-level control
4. **Standards Alignment:** Fits Rust Edition 2024, forbids `unsafe` code
5. **Maintainability:** Clear guidelines for when to use each pattern

### Implementation Guidelines

**Use Direct Event Handlers When:**

- Implementing widget internal behavior (button clicks, slider drags)
- Handling mouse-specific interactions (hover, drag, selection)
- Responding to scroll events
- Managing cursor styles

**Use Action System When:**

- Implementing editor commands (copy, paste, delete line)
- Creating rebindable shortcuts (Ctrl+S, Ctrl+K)
- Handling keyboard-driven operations (cursor movement, search)
- Building command palette integration

**Use Two-Phase Dispatch For:**

- Modal dialog outside-click dismissal (capture phase)
- Popup menu interaction blocking (capture phase)
- Normal UI event handling (bubble phase)
- Parent/child event coordination

---

## Consequences

### Benefits

1. **Comprehensive Input Support:**
   - Full mouse interaction coverage (click, drag, hover, scroll)
   - Complete keyboard handling (characters, shortcuts, multi-stroke)
   - Native IME support for international users
   - Cross-platform consistency

2. **Flexible Architecture:**
   - Rebindable keybindings without code changes
   - Clear separation between UI and command logic
   - Extensible action system for new commands
   - Platform abstraction for consistent behavior

3. **Production-Ready Patterns:**
   - Battle-tested in the reference editor
   - Known performance characteristics
   - Community support and examples
   - Active upstream development

4. **Alignment with Project Standards:**
   - Rust Edition 2024 compatible
   - `#![forbid(unsafe_code)]` compliant
   - GPUI framework integration
   - Cross-platform desktop application requirements

### Tradeoffs

1. **Learning Curve:**
   - Developers must understand both direct handlers and action system
   - Two-phase dispatch adds conceptual overhead
   - Focus management requires explicit tracking
   - **Mitigation:** Comprehensive documentation, clear implementation examples

2. **Architecture Complexity:**
   - Two event handling patterns to maintain
   - Need guidelines for pattern selection
   - Additional abstraction layers
   - **Mitigation:** Establish clear conventions, provide decision flowchart

3. **Documentation Limitations:**
   - GPUI documentation sparse in areas
   - Need to reference the reference codebase source code directly
   - IME implementation requires platform-specific knowledge
   - **Mitigation:** Create internal documentation from research findings

4. **Platform Inconsistencies:**
   - IME behavior differs across platforms
   - Some platform-specific quirks in event timing
   - Cursor positioning variations
   - **Mitigation:** Extensive cross-platform testing, fallback behaviors

### Implementation Dependencies

1. **Required Infrastructure:**
   - GPUI window and event loop setup
   - Dispatch tree configuration
   - Focus handle management system
   - Hitbox registration during paint phase

2. **Required Libraries:**
   - `gpui` - Event system and UI framework
   - `smallvec` - Efficient KeyContext storage
   - Platform-specific crates (windows-sys, cocoa, wayland-client)

3. **Related Components:**
   - PositionMap (from DisplayMap ADR) for coordinate transformation
   - Text buffer for selection and editing operations
   - Keymap configuration system for action bindings

---

## Implementation Plan

### Phase 1: Core Event Infrastructure (Weeks 1-2)

**Objectives:**

- Establish platform event abstraction
- Implement basic hitbox system
- Create focus management foundation

**Deliverables:**

1. Window event loop integration with GPUI
2. Hitbox registration in paint phase
3. Basic hit testing implementation
4. FocusHandle creation and tracking
5. Simple mouse click handlers
6. Basic keyboard event handlers

**Acceptance Criteria:**

- [ ] Window receives and processes platform events
- [ ] Hitbox-based hit testing operational
- [ ] Focus tracking functional
- [ ] Basic click handlers respond correctly
- [ ] Key events reach focused elements

### Phase 2: Mouse Interactions (Weeks 3-4)

**Objectives:**

- Implement text selection with mouse
- Add drag and hover support
- Integrate coordinate transformation

**Deliverables:**

1. Mouse-down/move/up drag detection
2. PositionMap integration for text coordinates
3. Shift-click range selection
4. Hover state management
5. Cursor style changes (IBeam, Arrow, PointingHand)
6. Scroll event handling

**Acceptance Criteria:**

- [ ] Click positioning in text buffer accurate
- [ ] Drag selection works smoothly
- [ ] Shift+click extends selection correctly
- [ ] Hover effects display appropriately
- [ ] Cursor styles change based on context
- [ ] Scrolling updates viewport correctly

### Phase 3: Keyboard and Actions (Weeks 5-6)

**Objectives:**

- Implement action system
- Configure keybindings
- Add multi-stroke support

**Deliverables:**

1. Action trait implementations for core commands
2. Keymap configuration system (JSON/TOML)
3. Action registration in dispatch tree
4. Multi-stroke keystroke accumulation
5. Context-aware action filtering
6. Keystroke timeout handling (1 second)

**Acceptance Criteria:**

- [ ] Actions dispatch correctly from keybindings
- [ ] Multi-stroke sequences work (e.g., Ctrl+K Ctrl+D)
- [ ] Context filtering routes actions appropriately
- [ ] Unmatched keystrokes fall through to text input
- [ ] Keybindings configurable without code changes

### Phase 4: Focus and Navigation (Week 7)

**Objectives:**

- Complete focus management
- Implement tab navigation
- Add focus visual indicators

**Deliverables:**

1. Tab order configuration system
2. Tab navigation implementation
3. Focus visual feedback (borders, highlights)
4. Focus event propagation
5. `contains_focused()` parent awareness
6. Programmatic focus changes

**Acceptance Criteria:**

- [ ] Tab key cycles through focusable elements
- [ ] Shift+Tab reverses tab order
- [ ] Focused elements display visual indicators
- [ ] Focus changes trigger appropriate events
- [ ] Parent elements aware of child focus state

### Phase 5: IME Support (Week 8)

**Objectives:**

- Implement PlatformInputHandler
- Add composition state tracking
- Test with CJK input methods

**Deliverables:**

1. PlatformInputHandler trait implementation
2. Composition range tracking
3. Candidate window positioning
4. Marked text rendering
5. Text replacement with composition
6. IME testing across platforms

**Acceptance Criteria:**

- [ ] Japanese input (Hiragana, Katakana, Kanji) works
- [ ] Chinese input with pinyin functions correctly
- [ ] Korean Hangul composition operational
- [ ] Candidate window positioned correctly
- [ ] Composition text visually distinct
- [ ] Cross-platform IME consistency verified

### Phase 6: Testing and Polish (Weeks 9-10)

**Objectives:**

- Comprehensive testing
- Cross-platform validation
- Performance optimization

**Deliverables:**

1. Unit tests for hit testing logic
2. Integration tests for event propagation
3. Cross-platform testing suite
4. Performance benchmarks for event handling
5. Documentation of patterns and best practices
6. Example implementations for common scenarios

**Acceptance Criteria:**

- [ ] Unit test coverage > 80% for event system
- [ ] All platforms pass integration tests
- [ ] Event handling latency < 16ms (60 FPS)
- [ ] No dropped input events under load
- [ ] Documentation complete and reviewed
- [ ] Performance benchmarks meet targets

---

## Testing Strategy

### Unit Tests

**Focus Areas:**

- Hitbox intersection logic
- Keystroke matching and accumulation
- Context predicate evaluation
- Focus handle reference counting
- Event propagation stopping conditions

**Implementation:**

```rust
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_hitbox_contains_point() {
        // Test hitbox bounds checking
    }

    #[test]
    fn test_multi_stroke_timeout() {
        // Test keystroke accumulation and timeout
    }

    #[test]
    fn test_focus_transfer() {
        // Test focus handle transfers
    }
}
```

### Integration Tests

**Focus Areas:**

- Full event flow from platform to handler
- Focus traversal with tab navigation
- IME composition sequences
- Two-phase dispatch order verification
- Action dispatch with multiple contexts

**Implementation:**
Place in `tests/` directory, test only public APIs.

### Platform-Specific Tests

**Windows:**

- WM_LBUTTONDOWN → MouseDownEvent conversion
- WM_KEYDOWN with modifier states
- WM_IME_COMPOSITION handling

**macOS:**

- NSEvent → PlatformInput conversion
- Precise scroll delta detection
- Native IME integration via NSTextInputClient

**Linux:**

- Wayland pointer events
- X11 XInput2 integration
- IBus/Fcitx IME compatibility

### Manual Testing Checklist

**Mouse Interactions:**

- [ ] Single click positions cursor correctly
- [ ] Double-click selects word
- [ ] Triple-click selects line
- [ ] Drag selects text smoothly
- [ ] Shift+click extends selection
- [ ] Hover changes cursor style
- [ ] Scroll updates viewport

**Keyboard Operations:**

- [ ] Character input appears in buffer
- [ ] Backspace/Delete remove characters
- [ ] Arrow keys move cursor
- [ ] Home/End navigate line boundaries
- [ ] Ctrl+Arrow moves by word
- [ ] Multi-stroke shortcuts work (Ctrl+K Ctrl+D)

**Focus Management:**

- [ ] Tab navigates between elements
- [ ] Shift+Tab reverses direction
- [ ] Focused element visually indicated
- [ ] Click changes focus appropriately
- [ ] Programmatic focus changes work

**IME Testing:**

- [ ] Japanese: Hiragana → Kanji conversion
- [ ] Chinese: Pinyin with candidate selection
- [ ] Korean: Hangul composition
- [ ] Composition text visually distinct
- [ ] Candidate window positioned correctly

---

## Acceptance Criteria

### Functional Requirements

1. **Mouse Events:**
   - [ ] Click, double-click, triple-click detection functional
   - [ ] Drag selection smooth and accurate
   - [ ] Hover effects respond correctly
   - [ ] Scroll events update viewport
   - [ ] Cursor styles change based on context

2. **Keyboard Events:**
   - [ ] Character input appears correctly
   - [ ] Keyboard shortcuts execute commands
   - [ ] Multi-stroke keybindings work
   - [ ] Modifier key combinations handled
   - [ ] Unmatched keystrokes become text input

3. **Focus Management:**
   - [ ] Tab navigation cycles focus
   - [ ] Visual focus indicators display
   - [ ] Keyboard events route to focused element
   - [ ] Programmatic focus changes supported
   - [ ] Parent focus awareness operational

4. **IME Support:**
   - [ ] CJK language input functional
   - [ ] Composition state tracked correctly
   - [ ] Candidate window positioned appropriately
   - [ ] Dead keys and combining characters work
   - [ ] Cross-platform consistency achieved

5. **Cross-Platform:**
   - [ ] Windows, macOS, Linux all functional
   - [ ] Consistent behavior across platforms
   - [ ] Platform-specific features working
   - [ ] Fallback behaviors for limitations

### Performance Requirements

1. **Latency:**
   - [ ] Event handling < 16ms (60 FPS target)
   - [ ] No perceptible input lag
   - [ ] Smooth drag operations

2. **Reliability:**
   - [ ] No dropped input events
   - [ ] Event order preserved
   - [ ] No event handler crashes

3. **Resource Usage:**
   - [ ] Minimal memory overhead for event structures
   - [ ] Efficient hit testing performance
   - [ ] No memory leaks in focus handles

### Code Quality Requirements

1. **Architecture:**
   - [ ] Clear separation: handlers vs actions
   - [ ] Documented pattern selection guidelines
   - [ ] Consistent implementation patterns
   - [ ] Minimal code duplication

2. **Testing:**
   - [ ] Unit test coverage > 80%
   - [ ] Integration tests for critical paths
   - [ ] Platform-specific tests passing
   - [ ] Manual testing checklist completed

3. **Documentation:**
   - [ ] Public APIs documented
   - [ ] Implementation examples provided
   - [ ] Pattern guidelines published
   - [ ] Architecture diagrams created

4. **Standards Compliance:**
   - [ ] Rust Edition 2024
   - [ ] `#![forbid(unsafe_code)]`
   - [ ] Project coding conventions followed
   - [ ] No compiler warnings

---

## Monitoring and Metrics

### Key Performance Indicators

1. **Event Latency:** Time from platform event to handler execution
   - Target: < 16ms (60 FPS)
   - Measurement: Instrumented event loop timing

2. **Input Responsiveness:** User-perceived input lag
   - Target: No perceptible delay
   - Measurement: Manual testing, user feedback

3. **Event Throughput:** Events processed per second
   - Target: > 1000 events/sec
   - Measurement: Synthetic event generation testing

4. **Memory Usage:** Event system memory overhead
   - Target: < 10MB base overhead
   - Measurement: Memory profiling tools

### Success Metrics

1. **Functionality:** All acceptance criteria passing
2. **Performance:** All KPIs meeting targets
3. **Quality:** Test coverage and documentation complete
4. **Usability:** Positive developer and user feedback

---

## Future Considerations

### Potential Enhancements

1. **Gesture Support:**
   - Pinch-to-zoom for editor scaling
   - Rotation gestures for viewport rotation
   - Three-finger swipe for navigation
   - **Dependency:** GPUI gesture event support

2. **Touch Input:**
   - Multi-touch text selection
   - Touch scrolling momentum
   - Touch-optimized UI elements
   - **Dependency:** Platform touch event abstraction

3. **Advanced IME:**
   - Inline candidate display
   - Custom composition rendering
   - Context-aware suggestions
   - **Dependency:** Platform IME API access

4. **Accessibility:**
   - Screen reader integration
   - Voice command support
   - Switch control compatibility
   - **Dependency:** Accessibility framework integration

5. **Performance Optimizations:**
   - Event batching for high-frequency input
   - Predictive event handling
   - GPU-accelerated hit testing
   - **Dependency:** Profiling data, GPUI enhancements

### Extensibility Points

1. **Custom Event Types:** Extension system for application-specific events
2. **Plugin Keybindings:** Allow plugins to register actions and keybindings
3. **Custom Input Handlers:** Support for specialized input devices
4. **Event Middleware:** Intercept and transform events before dispatch

---

## References

### Primary Sources

- [Reference Codebase Repository](https://github.com/zed-industries/zed) - Reference implementation
- [GPUI Documentation](https://docs.rs/gpui) - Framework API reference
- [GPUI Website](https://www.gpui.rs/) - Official framework site

### Architecture Documentation

- [GPUI Framework Overview](https://deepwiki.com/zed-industries/zed/2.2-gpui-framework)
- [Event Flow and Input Handling](https://deepwiki.com/zed-industries/zed/2.4-keybinding-and-action-dispatch)
- [Focus Management and IME](https://deepwiki.com/zed-industries/zed/2.5-keybinding-and-action-system)
- [GPUI Key Dispatch Documentation](https://github.com/zed-industries/zed/blob/main/crates/gpui/docs/key_dispatch.md)

### Tutorials and Examples

- [GPUI Interactivity Tutorial](https://blog.0xshadow.dev/posts/learning-gpui/gpui-interactivity/)
- [Building a Todo App in GPUI](https://blog.0xshadow.dev/posts/learning-gpui/gpui-todo-app/)
- [GPUI Input Example](https://github.com/zed-industries/zed/blob/main/crates/gpui/examples/input.rs)

### Community Resources

- [gpui-component Library](https://github.com/longbridge/gpui-component) - Production component library
- [GPUI Component Docs](https://longbridge.github.io/gpui-component/) - Component documentation
- [GPUI Tutorial Repository](https://github.com/hedge-ops/gpui-tutorial) - Learning examples

### Related Discussions

- [Discussion #31391: Additional Input Event Types](https://github.com/zed-industries/zed/discussions/31391)
- [Issue #42774: Input Component](https://github.com/zed-industries/zed/issues/42774)
- [Issue #12474: Hover Event Behavior](https://github.com/zed-industries/zed/issues/12474)
- [PR #22632: Context API Changes](https://github.com/zed-industries/zed/pull/22632)

---

## Appendix: Implementation Examples

### Example 1: Basic Click Handler

```rust
use gpui::*;

struct Button {
    label: SharedString,
    on_click: Option<Box<dyn Fn(&mut Window, &mut Context<Self>)>>,
}

impl Button {
    fn render(&self, cx: &mut Context<Self>) -> impl IntoElement {
        div()
            .on_mouse_up(MouseButton::Left, cx.listener(|this, _event, window, cx| {
                if let Some(handler) = &this.on_click {
                    handler(window, cx);
                }
            }))
            .child(self.label.clone())
    }
}
```

### Example 2: Action-Based Command

```rust
use gpui::*;

#[derive(Debug, Clone, PartialEq, Eq)]
#[gpui::action]
struct DeleteLine;

struct Editor {
    focus_handle: FocusHandle,
}

impl Editor {
    fn new(cx: &mut Context<Self>) -> Self {
        Self {
            focus_handle: cx.new_focus_handle(),
        }
    }

    fn delete_line(&mut self, _: &DeleteLine, window: &mut Window, cx: &mut Context<Self>) {
        // Delete current line implementation
        cx.notify();
    }

    fn render(&self, cx: &mut Context<Self>) -> impl IntoElement {
        div()
            .track_focus(&self.focus_handle)
            .key_context("editor")
            .on_action(cx.listener(Self::delete_line))
    }
}

// In keymap.json:
// {
//   "context": "editor",
//   "bindings": {
//     "ctrl-shift-k": "editor::DeleteLine"
//   }
// }
```

### Example 3: Text Selection with Mouse

```rust
use gpui::*;

struct TextArea {
    focus_handle: FocusHandle,
    selection: Option<Range<usize>>,
    selecting: bool,
}

impl TextArea {
    fn render(&self, cx: &mut Context<Self>) -> impl IntoElement {
        div()
            .track_focus(&self.focus_handle)
            .cursor(CursorStyle::IBeam)
            .on_mouse_down(MouseButton::Left, cx.listener(|this, event, window, cx| {
                let position = this.position_from_point(event.position);
                this.selection = Some(position..position);
                this.selecting = true;
                cx.notify();
            }))
            .on_mouse_move(cx.listener(|this, event, window, cx| {
                if this.selecting {
                    if let Some(ref mut selection) = this.selection {
                        let position = this.position_from_point(event.position);
                        selection.end = position;
                        cx.notify();
                    }
                }
            }))
            .on_mouse_up(MouseButton::Left, cx.listener(|this, _event, window, cx| {
                this.selecting = false;
                cx.notify();
            }))
    }

    fn position_from_point(&self, point: Point<Pixels>) -> usize {
        // Use PositionMap to convert pixel coordinates to buffer position
        todo!()
    }
}
```

### Example 4: IME Support

```rust
use gpui::*;

struct Editor {
    focus_handle: FocusHandle,
    composition_range: Option<Range<usize>>,
}

impl PlatformInputHandler for Editor {
    fn selected_text_range(&self, _ignore_disabled: bool) -> Option<UTF16Selection> {
        self.selection.as_ref().map(|range| UTF16Selection {
            range: range.clone(),
            reversed: false,
        })
    }

    fn marked_text_range(&self) -> Option<Range<usize>> {
        self.composition_range.clone()
    }

    fn bounds_for_range(&self, range: Range<usize>) -> Bounds<Pixels> {
        // Return bounds for IME candidate window positioning
        self.position_map.bounds_for_range(range)
    }

    fn replace_and_mark_text_in_range(
        &mut self,
        range: Option<Range<usize>>,
        new_text: &str,
        new_selected_range: Option<Range<usize>>,
    ) {
        // Handle IME composition
        if let Some(range) = range {
            self.buffer.replace_range(range, new_text);
            self.composition_range = new_selected_range;
        }
    }

    fn unmark_text(&mut self) {
        self.composition_range = None;
    }

    // ... other methods
}
```

---

**Document Version:** 1.0
**Authors:** Lead Technical Researcher
**Reviewed By:** Architecture Team
**Next Review:** After Phase 1 implementation completion

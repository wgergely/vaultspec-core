---
tags:
  - "#reference"
  - "#editor-event-handling"
date: 2026-02-04
related:
  - "[[2026-02-04-editor-event-handling-plan]]"
  - "[[2026-02-04-phase1-reference]]"
  - "[[2026-02-04-phase2-reference]]"
  - "[[2026-02-04-editor-event-handling-execution-summary]]"
---

# Reference Codebase: Editor Event Handling Audit

**Date:** 2026-02-04
**Scope:** Mouse, keyboard, and text input event handling in the reference editor
**Target:** Feature parity implementation for popup-prompt

---

## Executive Summary

This audit documents the reference implementation's comprehensive event handling architecture, covering mouse interactions, keyboard input, IME support, and platform-specific implementations. The findings provide a roadmap for implementing equivalent functionality in popup-prompt.

---

## 1. Core Architecture Components

### 1.1 Event Type Hierarchy

**File:** `gpui/src/input.rs`

The `PlatformInput` enum provides platform-agnostic input unification:

```rust
pub enum PlatformInput {
    KeyDown(KeyDownEvent),
    KeyUp(KeyUpEvent),
    ModifiersChanged(ModifiersChangedEvent),
    MouseDown(MouseDownEvent),
    MouseUp(MouseUpEvent),
    MousePressure(MousePressureEvent),  // Force touch
    MouseMove(MouseMoveEvent),
    MouseExited(MouseExitedEvent),
    ScrollWheel(ScrollWheelEvent),
    FileDrop(FileDropEvent),
}
```

**Traits:**

- `KeyEvent` - Common keyboard event interface
- `MouseEvent` - Common mouse event interface with `position()` and `modifiers()`

---

## 2. Mouse Event Handling

### 2.1 Hit Testing System

**File:** `gpui/src/window.rs:3976-4027`

Hit testing iterates hitboxes back-to-front with content mask intersection:

```rust
fn hitboxes_containing_point(&self, point: Point<Pixels>) -> Vec<HitboxId> {
    let mut result = Vec::new();
    for hitbox in self.rendered_frame.hitboxes.iter().rev() {
        let dominated = hitbox.content_mask.map_or(false, |mask| {
            !mask.bounds.contains(&point)
        });
        if !dominated && hitbox.bounds.contains(&point) {
            result.push(hitbox.id);
        }
    }
    result
}
```

### 2.2 Hitbox Behaviors

**File:** `gpui/src/window.rs:842-864`

Three distinct hitbox behaviors:

| Behavior | Description |
|----------|-------------|
| `Normal` | Standard event propagation |
| `BlockMouse` | Blocks all mouse events from passing through |
| `BlockMouseExceptScroll` | Allows scroll events, blocks others |

### 2.3 Two-Phase Dispatch

**Capture Phase (back→front):**

- Used for outside-click detection
- Parent elements intercept before children

**Bubble Phase (front→back):**

- Normal event handling
- Children handle before parents

### 2.4 Drag Detection

**File:** `gpui/src/window.rs`

Drag detection via `pressed_button` tracking:

```rust
struct WindowState {
    pressed_button: Option<MouseButton>,
    mouse_position: Point<Pixels>,
    // ...
}
```

---

## 3. Keyboard Event Handling

### 3.1 Dispatch Tree

**File:** `gpui/src/key_dispatch.rs`

Hierarchical node structure for focus-aware routing:

```rust
pub struct DispatchTree {
    nodes: Vec<DispatchNode>,
    focusable_node_ids: HashMap<FocusId, DispatchNodeId>,
    keystroke_matchers: HashMap<SmallVec<[KeyContext; 4]>, KeystrokeMatcher>,
    action_registrations: HashMap<TypeId, ActionRegistration>,
}
```

### 3.2 Multi-Stroke Keybindings

**File:** `gpui/src/key_dispatch.rs`

Accumulates keystrokes with 1-second timeout:

```rust
const KEYSTROKE_TIMEOUT: Duration = Duration::from_secs(1);

impl KeystrokeMatcher {
    pub fn push_keystroke(&mut self, keystroke: Keystroke, time: Instant) -> KeyMatch {
        if self.pending_keystrokes.last()
            .map_or(true, |(_, t)| time.duration_since(*t) > KEYSTROKE_TIMEOUT)
        {
            self.pending_keystrokes.clear();
        }
        self.pending_keystrokes.push((keystroke, time));
        self.match_pending()
    }
}
```

### 3.3 Context Matching

Bindings filtered by `KeyContext` stack depth:

```rust
pub struct KeyContext(SmallVec<[ContextEntry; 4]>);

pub struct ContextEntry {
    key: SharedString,
    value: Option<SharedString>,
}
```

### 3.4 Four-Stage Action Dispatch

**File:** `gpui/src/window.rs:4029-4207`

```
Global Capture → Window Capture → Window Bubble → Global Bubble
```

### 3.5 Keystroke Replay

Unmatched prefix sequences converted to text input when no binding matches.

---

## 4. Text Input & IME

### 4.1 InputHandler Trait

**File:** `gpui/src/platform.rs`

8 methods for text manipulation:

```rust
pub trait InputHandler: 'static {
    fn text_for_range(&mut self, range: Range<usize>) -> Option<String>;
    fn selected_text_range(&mut self, ignore_disabled_input: bool) -> Option<UTF16Selection>;
    fn marked_text_range(&self) -> Option<Range<usize>>;
    fn unmark_text(&mut self);
    fn replace_text_in_range(&mut self, replacement_range: Option<Range<usize>>, text: &str);
    fn replace_and_mark_text_in_range(
        &mut self,
        range: Option<Range<usize>>,
        new_text: &str,
        new_selected_range: Option<Range<usize>>,
    );
    fn bounds_for_range(&mut self, range: Range<usize>) -> Option<Bounds<Pixels>>;
    fn supports_character_insertion(&self) -> bool;
}
```

### 4.2 ElementInputHandler

**File:** `gpui/src/element_input_handler.rs`

Wrapper bridges views to platform input:

```rust
pub struct ElementInputHandler<V> {
    view: View<V>,
    element_bounds: Bounds<Pixels>,
    cx: AsyncWindowContext,
}
```

### 4.3 Composition Support

- `replace_and_mark_text_in_range()` - Handles IME composition
- `bounds_for_range()` - Positions candidate window

---

## 5. Platform-Specific Implementation

### 5.1 Windows

**File:** `gpui/src/platform/windows/events.rs`

- WM_* message loop processing
- `ToUnicode()` for key translation
- `WM_IME_*` messages for IME

### 5.2 macOS

**File:** `gpui/src/platform/mac/events.rs`

- NSEvent conversion
- Precise scroll delta detection
- Native IME integration via NSTextInputClient

### 5.3 Linux

**File:** `gpui/src/platform/linux/events.rs`

- Wayland protocol support
- X11 XIinput2 integration
- IBus/Fcitx IME integration

---

## 6. Editor-Specific Events

### 6.1 Cursor Movement

**File:** `editor/src/editor.rs`

```rust
pub fn move_up(&mut self, _: &MoveUp, cx: &mut ViewContext<Self>) { ... }
pub fn move_down(&mut self, _: &MoveDown, cx: &mut ViewContext<Self>) { ... }
pub fn move_left(&mut self, _: &MoveLeft, cx: &mut ViewContext<Self>) { ... }
pub fn move_right(&mut self, _: &MoveRight, cx: &mut ViewContext<Self>) { ... }
```

### 6.2 Text Selection

**File:** `editor/src/element.rs`

- Click positioning via `position_map`
- Triple-click line selection
- Shift+click range extension
- Alt+click column/block selection

### 6.3 Buffer Modifications

**File:** `editor/src/editor.rs`

- Transaction-based undo/redo
- Multi-cursor support
- Snippet expansion

---

## 7. Key Implementation Patterns

### 7.1 Stateless Event Handlers

Uses closure captures with `cx.listener()` to avoid borrowing issues:

```rust
div()
    .on_mouse_down(MouseButton::Left, cx.listener(|this, event, cx| {
        this.handle_click(event, cx);
    }))
```

### 7.2 Phase-Based Interception

Capture phase for outside-click detection:

```rust
div()
    .on_mouse_down_out(cx.listener(|this, _, cx| {
        this.dismiss(cx);
    }))
```

### 7.3 Focus Management

Explicit `FocusHandle` tracking:

```rust
pub struct Editor {
    focus_handle: FocusHandle,
    // ...
}

impl FocusableView for Editor {
    fn focus_handle(&self, _cx: &AppContext) -> FocusHandle {
        self.focus_handle.clone()
    }
}
```

### 7.4 Hitbox Registration Order

Critical to register in paint order (front-to-back) for correct hit testing.

---

## 8. Critical Files Reference Map

### Core GPUI

| File | Purpose | Key Lines |
|------|---------|-----------|
| `gpui/src/input.rs` | Event types & traits | Full file |
| `gpui/src/key_dispatch.rs` | Keyboard dispatch tree | Full file |
| `gpui/src/keymap.rs` | Keybinding definitions | Full file |
| `gpui/src/window.rs` | Event processing | 3976-4207 |
| `gpui/src/element_input_handler.rs` | IME bridge | Full file |

### Platform Layer

| File | Purpose |
|------|---------|
| `gpui/src/platform/windows/events.rs` | Windows input |
| `gpui/src/platform/mac/events.rs` | macOS input |
| `gpui/src/platform/linux/events.rs` | Linux input |

### Editor Layer

| File | Purpose | Key Lines |
|------|---------|-----------|
| `editor/src/element.rs` | Editor rendering & mouse | 800-1200 |
| `editor/src/editor.rs` | Editor logic & keyboard | Full file |

---

## 9. Implementation Recommendations for Popup-Prompt

### Phase 1 - Essential (MVP)

1. **Hitbox-based mouse targeting system**
   - Implement hitbox registration during paint
   - Back-to-front hit testing
   - Content mask intersection

2. **Focus-aware dispatch tree**
   - FocusHandle management
   - KeyContext stack
   - Focus event propagation

3. **Two-phase event propagation**
   - Capture phase for modal/popup dismissal
   - Bubble phase for normal handling

4. **Basic multi-stroke keybindings**
   - Keystroke accumulation
   - Simple timeout handling

### Phase 2 - Enhanced

1. **Complete multi-stroke timeout handling**
   - 1-second timeout
   - Keystroke replay for unmatched prefixes

2. **Context-aware keymap matching**
   - KeyContext predicates
   - Binding priority resolution

3. **IME composition support**
   - InputHandler trait implementation
   - Marked text handling
   - Candidate window positioning

4. **Platform-specific input normalization**
   - Keyboard layout detection
   - Dead key handling

### Phase 3 - Polish

1. **Force-touch pressure events**
   - MousePressureEvent handling

2. **Precise scroll delta handling**
   - Pixel vs line scroll detection
   - Momentum scrolling

3. **Cross-platform keyboard layout adaptation**
   - Layout-independent shortcuts

---

## 10. Testing Strategy

### Unit Tests

- Hitbox intersection logic
- Keystroke matching
- Context predicate evaluation

### Integration Tests

- Focus traversal
- Event propagation order
- IME composition sequences

### Platform Tests

- Windows: WM_* message handling
- macOS: NSEvent conversion
- Linux: Wayland/X11 parity

---

## 11. Dependencies

```toml
[dependencies]
smallvec = "1.11"  # KeyContext storage
# Platform-specific:
# windows-sys (Windows)
# cocoa, objc (macOS)
# wayland-client, x11rb (Linux)
```

---

## Appendix: Event Flow Diagram

```
Platform Event (OS)
        │
        ▼
┌─────────────────┐
│ Platform Layer  │  (windows/mac/linux)
│ Event Conversion│
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  PlatformInput  │  (unified enum)
└────────┬────────┘
         │
    ┌────┴────┐
    │         │
    ▼         ▼
┌───────┐ ┌───────┐
│ Mouse │ │ Key   │
│ Event │ │ Event │
└───┬───┘ └───┬───┘
    │         │
    ▼         ▼
┌───────┐ ┌────────────┐
│ Hit   │ │ Dispatch   │
│ Test  │ │ Tree       │
└───┬───┘ └─────┬──────┘
    │           │
    ▼           ▼
┌─────────────────────┐
│  Capture Phase      │
│  (back → front)     │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Bubble Phase       │
│  (front → back)     │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Handler Execution  │
└─────────────────────┘
```

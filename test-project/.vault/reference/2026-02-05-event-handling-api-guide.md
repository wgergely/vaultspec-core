---
tags:
  - "#reference"
  - "#event-handling"
date: 2026-02-05
related:
  - "[[2026-02-04-editor-event-handling]]"
  - "[[2026-02-05-editor-demo-events-reference]]"
  - "[[2026-02-04-editor-event-handling-execution-summary]]"
---

# Event Handling API Guide

Complete guide to using the pp-editor-events API for building interactive editor components.

## Table of Contents

1. [Overview](#overview)
2. [Mouse Events](#mouse-events)
3. [Keyboard Events](#keyboard-events)
4. [Focus Management](#focus-management)
5. [Actions](#actions)
6. [Text Selection](#text-selection)
7. [IME Support](#ime-support)
8. [Best Practices](#best-practices)

## Overview

The event handling system uses GPUI's hybrid model:

- **Direct Handlers**: For mouse interactions (position-dependent)
- **Action System**: For keyboard commands (semantic, rebindable)

### Core Concepts

- **Hitbox**: Rectangular region that receives mouse events
- **FocusHandle**: Strong reference for keyboard focus tracking
- **Action**: Semantic command that can be triggered multiple ways
- **KeyContext**: UI context for filtering keybindings

## Mouse Events

### Click Handling

```rust
use pp_editor_events::prelude::*;
use gpui::{div, px, MouseButton};

fn render_button(cx: &mut WindowContext) -> impl IntoElement {
    div()
        .size(px(100.0))
        .on_mouse_down(MouseButton::Left, cx.listener(|this, event, window, cx| {
            println!("Button pressed at {:?}", event.position);
        }))
        .on_mouse_up(MouseButton::Left, cx.listener(|this, event, window, cx| {
            println!("Button released");
            this.handle_click();
            cx.notify();
        }))
}
```

### Hover Effects

```rust
use pp_editor_events::cursor::CursorStyle;

fn render_hoverable(cx: &mut WindowContext) -> impl IntoElement {
    div()
        .on_hover(cx.listener(|this, is_hovering, window, cx| {
            if is_hovering {
                // Show hover state
            }
        }))
        .cursor(CursorStyle::PointingHand)
}
```

### Drag and Drop

```rust
use pp_editor_events::selection::SelectionDragState;

struct Editor {
    drag_state: Option<SelectionDragState>,
}

impl Editor {
    fn handle_mouse_down(&mut self, position: Point<Pixels>) {
        self.drag_state = Some(SelectionDragState::new(position));
    }

    fn handle_mouse_move(&mut self, position: Point<Pixels>) {
        if let Some(drag) = &mut self.drag_state {
            drag.update(position);
            // Update selection based on drag
        }
    }

    fn handle_mouse_up(&mut self) {
        if let Some(drag) = &mut self.drag_state {
            drag.end();
        }
        self.drag_state = None;
    }
}
```

## Keyboard Events

### Basic Key Handling

```rust
fn render_input(cx: &mut WindowContext) -> impl IntoElement {
    div()
        .track_focus(&self.focus_handle)
        .on_key_down(cx.listener(|this, event, window, cx| {
            match event.keystroke.key.as_str() {
                "backspace" => this.delete_char(),
                "enter" => this.insert_newline(),
                _ => {}
            }
            cx.notify();
        }))
}
```

### Actions (Recommended)

```rust
use gpui::actions;

// Define actions
actions!(editor, [DeleteLine, MoveCursorUp, MoveCursorDown, Save]);

// Register handlers
fn register_actions(cx: &mut WindowContext) {
    cx.on_action(|this: &mut Editor, _: &DeleteLine, cx| {
        this.delete_current_line();
        cx.notify();
    });

    cx.on_action(|this: &mut Editor, _: &Save, cx| {
        this.save();
        cx.notify();
    });
}
```

### Keybindings Configuration

Create `keymap.toml`:

```toml
[[bindings]]
context = "editor"
keystroke = "ctrl-s"
action = "workspace::Save"

[[bindings]]
context = "editor"
keystroke = "ctrl-k ctrl-d"
action = "editor::DeleteLine"

[[bindings]]
context = "editor && text_area"
keystroke = "enter"
action = "editor::InsertNewline"
```

## Focus Management

### Creating Focusable Elements

```rust
struct TextInput {
    focus_handle: FocusHandle,
}

impl TextInput {
    fn new(cx: &mut WindowContext) -> Self {
        Self {
            focus_handle: cx.new_focus_handle(),
        }
    }

    fn render(&mut self, cx: &mut WindowContext) -> impl IntoElement {
        div()
            .track_focus(&self.focus_handle)
            .when(self.focus_handle.is_focused(cx), |el| {
                el.border_color(gpui::blue())
            })
    }
}
```

### Programmatic Focus Control

```rust
// Transfer focus to element
cx.focus(&self.input_focus_handle);

// Check if focused
if self.focus_handle.is_focused(cx) {
    // Element has focus
}

// Check if child is focused
if self.focus_handle.contains_focused(cx) {
    // Some descendant has focus
}
```

### Tab Navigation

```rust
use pp_editor_events::tab_order::TabIndex;

div()
    .tab_index(TabIndex::new(0))  // In tab order
    .track_focus(&self.focus_handle)

// Remove from tab order (focusable by click/code only)
div()
    .tab_index(TabIndex::new(-1))
    .track_focus(&self.focus_handle)
```

### Focus Events

```rust
div()
    .on_focus(cx.listener(|this, event, window, cx| {
        println!("Gained focus: {:?}", event.focus_id);
        cx.notify();
    }))
    .on_blur(cx.listener(|this, event, window, cx| {
        println!("Lost focus: {:?}", event.focus_id);
        cx.notify();
    }))
```

## Actions

### Defining Actions

```rust
use gpui::actions;

// Module-scoped actions
actions!(
    editor,
    [
        MoveCursor,
        DeleteLine,
        InsertNewline,
        SelectAll,
    ]
);

// Actions with data
#[derive(Clone, PartialEq)]
pub struct MoveCursor {
    pub direction: Direction,
    pub select: bool,
}

actions!(editor, [MoveCursor]);
```

### Registering Action Handlers

```rust
impl Editor {
    fn register_actions(&mut self, cx: &mut WindowContext) {
        cx.on_action(|this: &mut Self, action: &MoveCursor, cx| {
            this.move_cursor(action.direction, action.select);
            cx.notify();
        });

        cx.on_action(|this: &mut Self, _: &DeleteLine, cx| {
            this.delete_line();
            cx.notify();
        });
    }
}
```

### Context-Aware Actions

```rust
use pp_editor_events::key_context::KeyContext;

div()
    .track_focus(&self.focus_handle)
    .key_context(KeyContext::new().add_entry("editor").add_entry("text_area"))
```

## Text Selection

### Creating Selections

```rust
use pp_editor_events::selection::{Selection, SelectionSet};
use pp_editor_events::position_map::Position;

// Single selection
let selection = Selection::new(
    Position::new(0, 5),   // Start: line 0, column 5
    Position::new(0, 10),  // End: line 0, column 10
);

// Multiple selections (multi-cursor)
let mut selections = SelectionSet::new();
selections.add(Selection::new(Position::new(0, 5), Position::new(0, 10)));
selections.add(Selection::new(Position::new(1, 0), Position::new(1, 5)));
```

### Mouse Selection

```rust
impl Editor {
    fn handle_mouse_down(&mut self, event: &MouseDownEvent, cx: &mut WindowContext) {
        let position = self.position_map.position_from_point(event.position);

        if event.modifiers.shift() {
            // Extend selection
            self.extend_selection_to(position);
        } else {
            // New selection
            self.set_cursor(position);
        }
    }

    fn handle_mouse_drag(&mut self, event: &MouseMoveEvent, cx: &mut WindowContext) {
        if self.is_dragging {
            let position = self.position_map.position_from_point(event.position);
            self.extend_selection_to(position);
        }
    }
}
```

## IME Support

### Implementing PlatformInputHandler

```rust
use pp_editor_events::ime::EditorInputHandler;
use std::sync::{Arc, RwLock};

struct Editor {
    input_handler: EditorInputHandler<MyPositionMap>,
}

impl Editor {
    fn new(cx: &mut WindowContext) -> Self {
        let position_map = Arc::new(RwLock::new(MyPositionMap::new()));
        let text_accessor = Arc::new(RwLock::new(Box::new(move || {
            // Return current text content
            "Hello, World!".to_string()
        })));

        Self {
            input_handler: EditorInputHandler::new(position_map, text_accessor),
        }
    }
}
```

### Handling Composition

```rust
impl Editor {
    fn render_composition(&self, cx: &mut WindowContext) {
        if let Some(composition) = self.input_handler.composition_state() {
            if composition.is_composing() {
                let range = composition.marked_text_range();
                // Render composition underline/highlight
            }
        }
    }
}
```

## Best Practices

### DO

✅ Use actions for keyboard commands (rebindable, semantic)
✅ Use direct handlers for mouse events (position-dependent)
✅ Always provide focus indicators (WCAG compliance)
✅ Make all functionality keyboard-accessible
✅ Use appropriate cursor styles
✅ Batch state updates with `cx.notify()`
✅ Handle platform differences through GPUI abstractions

### DON'T

❌ Don't use direct handlers for keyboard (use actions instead)
❌ Don't create keyboard traps (always allow Tab out)
❌ Don't skip focus indicators for keyboard users
❌ Don't make functionality mouse-only
❌ Don't block events unnecessarily
❌ Don't call `cx.notify()` in tight loops
❌ Don't assume platform-specific behavior

### Performance Tips

- Keep hitbox count < 200 per frame
- Use simple keystroke sequences (1-2 keys)
- Avoid deep context nesting (< 5 levels)
- Batch multiple selections into SelectionSet
- Use position_map caching for frequent queries

### Accessibility Checklist

- [ ] All interactive elements are focusable
- [ ] Tab order is logical
- [ ] Focus indicators are visible (2px, 3:1 contrast)
- [ ] All functionality available via keyboard
- [ ] No keyboard traps (can always Tab out)
- [ ] Screen reader compatible (programmatic state)
- [ ] Sufficient contrast for all UI elements
- [ ] Skip navigation for repeated content

## Examples

See `crates/pp-editor-events/examples/` for complete working examples:

- `basic_button.rs`: Click handling and hover effects
- `text_input.rs`: Keyboard input and selection
- `tab_navigation.rs`: Focus management and tab order

## API Reference

Full API documentation available via:

```bash
cargo doc --open --manifest-path crates/pp-editor-events/Cargo.toml
```

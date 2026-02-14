---
tags:
  - "#reference"
  - "#editor-demo"
date: 2026-02-05
related:
  - "[[2026-02-05-editor-demo-research]]"
  - "[[2026-02-04-editor-event-handling]]"
  - "[[2026-02-04-editor-event-handling-execution-summary]]"
  - "[[event-handling-guide]]"
---

# Event Handling Reference: pp-editor-events vs Zed GPUI

## Crate(s)

- **Ours**: `pp-editor-events` (`crates/pp-editor-events/src/`)
- **Zed**: `gpui` (`ref/zed/crates/gpui/src/`), `editor` (`ref/zed/crates/editor/src/editor.rs`)

## File(s)

### pp-editor-events

| File | Purpose |
|------|---------|
| `lib.rs` | Crate root, module declarations, prelude |
| `actions.rs` | Action definitions via `gpui::actions!()` macro |
| `dispatch.rs` | DispatchNodeId, DispatchPhase, DispatchResult, ActionRegistration |
| `keystroke.rs` | Keystroke parsing and modifier handling |
| `keystroke_matcher.rs` | Multi-stroke sequence matching with timeout |
| `keymap.rs` | KeyBinding, Keymap, keystroke-to-action mapping |
| `key_context.rs` | KeyContext with identifier and key-value entries |
| `focus.rs` | FocusHandle re-exports, FocusEvent/BlurEvent, FocusChangeTracker, FocusRestorer, FocusHistory |
| `hit_test.rs` | HitTest algorithm (reverse-order scan with behavior filtering) |
| `hitbox.rs` | HitboxId, Hitbox, HitboxBehavior enum |
| `mouse.rs` | MouseHandler trait, re-exports of GPUI mouse events |
| `keyboard.rs` | KeyboardHandler trait |
| `drag.rs` | DragState state machine (Idle/Pressed/Dragging) |
| `selection.rs` | Selection, SelectionSet, SelectionDragState |
| `position_map.rs` | Position, PositionMap trait, StubPositionMap |
| `ime/composition.rs` | CompositionRange, CompositionState |
| `ime/handler.rs` | EditorInputHandler (standalone, not trait-based) |
| `ime/candidate.rs` | CandidateWindowPositioner |
| `ime/rendering.rs` | CompositionRenderer |
| `scroll.rs` | ScrollDelta, ScrollHandler |
| `hover.rs` | HoverChange, HoverState |
| `tab_navigation.rs` | TabNavigator, TabNavigationExt |
| `tab_order.rs` | TabIndex, TabOrderRegistry, TabStop |
| `window.rs` | EventWindow |

### Zed (GPUI + Editor)

| File | Purpose |
|------|---------|
| `gpui/src/input.rs` | `EntityInputHandler` trait, `ElementInputHandler<V>` adapter |
| `gpui/src/key_dispatch.rs` | `DispatchTree`, `DispatchNode`, keystroke dispatch algorithm |
| `gpui/src/action.rs` | `Action` trait, `actions!()` macro, `ActionRegistry` |
| `gpui/src/interactive.rs` | Platform input events (KeyDown, MouseDown, etc.), `PlatformInput` |
| `gpui/src/keymap.rs` | `Keymap`, `KeyBinding` definitions |
| `gpui/src/window.rs` | `HitboxId`, `Hitbox`, `HitboxBehavior`, `HitTest`, `insert_hitbox()`, `hit_test()` |
| `editor/src/editor.rs:27454` | `impl EntityInputHandler for Editor` |

---

## 1. Input Handler Trait

### Zed: `EntityInputHandler`

**File**: `ref/zed/crates/gpui/src/input.rs`

Zed defines `EntityInputHandler` as a trait that views implement to receive text input from the platform IME layer. The trait methods operate within the GPUI entity/context system:

```rust
pub trait EntityInputHandler: 'static + Sized {
    fn text_for_range(&mut self, range: Range<usize>, adjusted_range: &mut Option<Range<usize>>, window: &mut Window, cx: &mut Context<Self>) -> Option<String>;
    fn selected_text_range(&mut self, ignore_disabled_input: bool, window: &mut Window, cx: &mut Context<Self>) -> Option<UTF16Selection>;
    fn marked_text_range(&self, window: &mut Window, cx: &mut Context<Self>) -> Option<Range<usize>>;
    fn unmark_text(&mut self, window: &mut Window, cx: &mut Context<Self>);
    fn replace_text_in_range(&mut self, range: Option<Range<usize>>, text: &str, window: &mut Window, cx: &mut Context<Self>);
    fn replace_and_mark_text_in_range(&mut self, range: Option<Range<usize>>, new_text: &str, new_selected_range: Option<Range<usize>>, window: &mut Window, cx: &mut Context<Self>);
    fn bounds_for_range(&mut self, range_utf16: Range<usize>, element_bounds: Bounds<Pixels>, window: &mut Window, cx: &mut Context<Self>) -> Option<Bounds<Pixels>>;
    fn character_index_for_point(&mut self, point: Point<Pixels>, window: &mut Window, cx: &mut Context<Self>) -> Option<usize>;
    fn accepts_text_input(&self, _window: &mut Window, _cx: &mut Context<Self>) -> bool { true }
}
```

Key detail: `ElementInputHandler<V>` wraps the trait to bridge to the lower-level `InputHandler` trait via `self.view.update(cx, ...)`, adapting the entity context. The `element_bounds` are captured at paint time and passed into `bounds_for_range`.

In Zed's Editor (`editor.rs:27454`), the implementation:

- Uses `MultiBufferOffsetUtf16` for precise UTF-16 offset handling with bias (Left/Right)
- Clips ranges to valid positions via `snapshot.clip_offset_utf16()`
- Tracks IME composition via `InputComposition` text highlights
- Wraps text replacement in transactions for undo grouping
- Emits `EditorEvent::InputHandled` for input telemetry
- Respects `self.input_enabled` to suppress IME when disabled

### Ours: `EditorInputHandler<P>`

**File**: `crates/pp-editor-events/src/ime/handler.rs`

Our implementation is a **standalone struct** (not a GPUI trait impl) using `Arc<RwLock<...>>` for thread safety:

```rust
pub struct EditorInputHandler<P: PositionMap> {
    composition: Arc<RwLock<CompositionState>>,
    position_map: Arc<RwLock<P>>,
    selection: Arc<RwLock<Option<UTF16Selection>>>,
    text_accessor: Arc<RwLock<Box<dyn Fn() -> String + Send + Sync>>>,
}
```

### Gap Analysis: Input Handler

| Aspect | Zed | Ours | Gap |
|--------|-----|------|-----|
| Trait integration | Implements `EntityInputHandler` trait from GPUI | Standalone struct, no trait impl | **CRITICAL**: Must implement `EntityInputHandler` to work with GPUI platform input |
| Context access | Has Window + Context<Self> in every method | Uses Arc<RwLock> with closures | Need to refactor to entity-based pattern |
| UTF-16 handling | Full `MultiBufferOffsetUtf16` with bias clipping | Manual UTF-16 encode/decode via `encode_utf16()` | Need proper offset system with bias |
| Text replacement | Actually replaces text in buffer via transactions | Stubs: `replace_text_in_range` returns `Err` | **BLOCKER**: No buffer integration yet |
| Composition tracking | Uses `InputComposition` highlight markers on buffer | Tracks `CompositionState` in separate RwLock | Decoupled from buffer; needs integration |
| Transaction grouping | `buffer.group_until_transaction(transaction, cx)` | Not implemented | Needed for proper undo during IME |
| Input disabling | `self.input_enabled` flag checked in every method | Always returns `true` | Need input enable/disable support |
| `bounds_for_range` | Receives `element_bounds` from paint-time capture | Delegates to `PositionMap` (stub) | PositionMap approach is sound but needs real data |

---

## 2. IME Composition

### Zed: `InputComposition` Highlight System

**File**: `ref/zed/crates/editor/src/editor.rs:27500-27653`

Zed uses the editor's text highlight system to track IME composition:

- `marked_text_range()`: Returns the range of `InputComposition` highlights
- `unmark_text()`: Clears `InputComposition` highlights and takes `ime_transaction`
- `replace_and_mark_text_in_range()`: Complex multi-selection-aware composition:
  1. Resolves marked ranges or falls back to selection replacement ranges
  2. Emits `EditorEvent::InputHandled` with range-to-replace
  3. Applies text to all selections simultaneously
  4. Re-highlights the composition range with `HighlightStyle` (underline)
  5. Groups undo operations via `ime_transaction`
- `replace_text_in_range()`: Final commit of IME text -- replaces, handles input, unmarks

### Ours: `CompositionState`

**File**: `crates/pp-editor-events/src/ime/composition.rs`

Our composition tracking is a simple state container:

```rust
pub struct CompositionState {
    composition: Option<CompositionRange>,
}
pub struct CompositionRange {
    range: Range<usize>,
    selected: Option<Range<usize>>,
}
```

### Gap Analysis: IME

| Aspect | Zed | Ours | Gap |
|--------|-----|------|-----|
| Composition storage | Integrated into buffer highlight system | Separate `CompositionState` struct | Need to bridge to buffer highlights |
| Multi-selection | Applies composition across all selections | Single composition range | No multi-cursor support yet |
| Transaction grouping | Groups all IME edits into single undo | No transaction support | Need undo integration |
| Underline rendering | Uses `HighlightStyle { underline }` | Has `CompositionRenderer` module (content unknown) | Verify rendering approach |
| Candidate positioning | Via `bounds_for_range` on entity handler | Has `CandidateWindowPositioner` | Verify implementation |

---

## 3. Keystroke Matching

### Zed: `DispatchTree::dispatch_key()`

**File**: `ref/zed/crates/gpui/src/key_dispatch.rs:483-519`

Zed's keystroke dispatch is a **recursive algorithm** integrated into the dispatch tree:

```
dispatch_key(input, keystroke, dispatch_path):
  1. Append keystroke to input
  2. Query keymap with full input + context_stack from dispatch_path
  3. If pending: return DispatchResult { pending: input, pending_has_binding }
  4. If bindings found: return DispatchResult { bindings }
  5. If single keystroke with no match: return empty result
  6. Otherwise: replay_prefix(input) -- find longest matching prefix, recurse
```

The `replay_prefix` algorithm handles the case where a multi-stroke sequence partially matches and then fails -- it replays the longest matching prefix as bindings and recursively processes the suffix.

The `flush_dispatch()` method converts all pending keystrokes to replay events on timeout.

Key data structures:

- `DispatchResult { pending, pending_has_binding, bindings, to_replay, context_stack }`
- `Replay { keystroke, bindings }` -- a keystroke that needs to be replayed with its matched bindings

### Ours: `KeystrokeMatcher`

**File**: `crates/pp-editor-events/src/keystroke_matcher.rs`

Our matcher is a simpler standalone state machine:

```
push_keystroke(keystroke, now, keymap, context_stack):
  1. Check timeout -- if expired, return Timeout(old_pending)
  2. Add keystroke to pending buffer
  3. Query keymap.match_keystrokes(pending, context_stack)
  4. Return Complete/Pending/NoMatch
```

### Gap Analysis: Keystroke Matching

| Aspect | Zed | Ours | Gap |
|--------|-----|------|-----|
| Dispatch path integration | Queries bindings against dispatch_path nodes | Uses flat context_stack | Dispatch tree integration needed |
| Prefix replay | Recursive replay_prefix finds longest match | Returns NoMatch for failed sequences | **SIGNIFICANT**: No partial prefix replay |
| Pending + bindings | Can have both pending AND bindings simultaneously | Mutually exclusive states | Need `pending_has_binding` flag |
| Timeout flush | `flush_dispatch()` recursively replays all pending | `flush_timeout()` returns raw pending | Need recursive replay on flush |
| `to_replay` mechanism | Returns `SmallVec<[Replay; 1]>` with binding info | Returns `SmallVec<[Keystroke; 4]>` without bindings | Replay needs binding context |
| Tree-aware context | Context stack built from dispatch_path nodes | Passed externally as `&[KeyContext]` | Architecture matches (context comes from tree) |

---

## 4. Hit Testing

### Zed: `Frame::hit_test()`

**File**: `ref/zed/crates/gpui/src/window.rs:842-864`

Zed's hit test is a simple reverse-iteration algorithm:

```rust
pub(crate) fn hit_test(&self, position: Point<Pixels>) -> HitTest {
    let mut hit_test = HitTest::default();
    for hitbox in self.hitboxes.iter().rev() {
        let bounds = hitbox.bounds.intersect(&hitbox.content_mask.bounds);
        if bounds.contains(&position) {
            hit_test.ids.push(hitbox.id);
            if !set_hover_hitbox_count && hitbox.behavior == HitboxBehavior::BlockMouseExceptScroll {
                hit_test.hover_hitbox_count = hit_test.ids.len();
                set_hover_hitbox_count = true;
            }
            if hitbox.behavior == HitboxBehavior::BlockMouse {
                break;
            }
        }
    }
    if !set_hover_hitbox_count {
        hit_test.hover_hitbox_count = hit_test.ids.len();
    }
    hit_test
}
```

Hitboxes are registered during prepaint via `Window::insert_hitbox()` which:

- Takes `bounds` and `behavior`
- Captures the current `content_mask` from the mask stack
- Auto-increments `next_hitbox_id`
- Stores in `next_frame.hitboxes`

The `HitboxId` provides `is_hovered(window)` and `should_handle_scroll(window)` convenience methods that query `window.mouse_hit_test`.

### Ours: `HitTest::test()`

**File**: `crates/pp-editor-events/src/hit_test.rs:63-96`

Our algorithm is a **faithful reproduction** of Zed's:

```rust
pub fn test(hitboxes: &[Hitbox], point: Point<Pixels>) -> Self {
    // Identical reverse-iteration with BlockMouse/BlockMouseExceptScroll handling
}
```

### Gap Analysis: Hit Testing

| Aspect | Zed | Ours | Status |
|--------|-----|------|--------|
| Algorithm | Reverse-iteration with content_mask intersection | Identical algorithm | **ALIGNED** |
| HitboxBehavior variants | Normal, BlockMouse, BlockMouseExceptScroll | Identical variants | **ALIGNED** |
| HitboxId methods | `is_hovered(window)`, `should_handle_scroll(window)` | `is_hovered(id)`, `should_handle_scroll(id)` | Ours takes id as param vs querying window state |
| Registration | `Window::insert_hitbox()` during prepaint | No registration system (standalone `Hitbox::new()`) | Need prepaint integration |
| Window integration | `window.mouse_hit_test` cached per frame | `HitTest::test()` called on demand | Need per-frame caching |
| Content mask | Captured from `window.content_mask()` stack at registration | Passed as constructor param | Architecturally equivalent |

---

## 5. Selection Drag

### Zed: Editor Selection via Mouse

**File**: `ref/zed/crates/editor/src/editor.rs` (mouse handlers dispersed through 30k+ lines)

Zed's selection drag is handled through GPUI's mouse event handlers registered on the `EditorElement`:

- `on_mouse_down` -> `Editor::mouse_down()` which:
  - Hit tests against the editor element
  - Determines click type (single/double/triple via `click_count`)
  - Sets selection anchor from display point
  - Initiates drag tracking
- `on_mouse_move` during drag:
  - Converts position to display point
  - Extends selection from anchor to current point
  - Handles auto-scroll when dragging near edges
- `on_mouse_up` -> Completes selection

Zed uses `SelectionSet` with full multi-cursor support (disjoint selections with stable IDs).

### Ours: `DragState` + `SelectionDragState`

**Files**: `crates/pp-editor-events/src/drag.rs`, `crates/pp-editor-events/src/selection.rs`

We have two separate state machines:

1. **Generic `DragState`** (Idle -> Pressed -> Dragging): Tracks button, start/current position, delta
2. **`SelectionDragState`** (Idle -> Dragging { anchor, extend_existing }): Text selection specific

And `Selection`/`SelectionSet` for the actual selection data:

- `Selection { anchor: Position, head: Position }`
- `SelectionSet { primary: Selection }` -- single selection only

### Gap Analysis: Selection Drag

| Aspect | Zed | Ours | Gap |
|--------|-----|------|-----|
| Multi-cursor | Full `Vec<Selection>` with stable IDs | Single primary selection only | **Future work** (by design) |
| Click count | Tracks single/double/triple click for word/line select | Not tracked | Need click count detection |
| Auto-scroll | Scrolls when dragging near edges | Not implemented | Need scroll-on-drag |
| Display point conversion | Uses `PositionMap` to convert pixel to display point | Has `PositionMap` trait (stub) | Need real position mapping |
| Drag threshold | GPUI handles drag detection | `DragState` transitions on any movement | May need minimum drag distance |
| Extend with shift | Shift-click extends existing selection | `SelectionDragState.extend_existing` flag | Flag exists but unused |

---

## 6. Action System

### Zed

**File**: `ref/zed/crates/gpui/src/action.rs`

Zed's action system:

- `Action` trait: `Any + Send` with `boxed_clone()`, `partial_eq()`, `name()`, `build(serde_json::Value)`
- `actions!()` macro: Generates unit structs with derive `Action`
- Complex actions: `#[derive(Action)]` with `#[action(namespace = editor)]`
- Actions support JSON deserialization for keymap config files
- `ActionRegistry` stores builders by TypeId for runtime construction

### Ours

**File**: `crates/pp-editor-events/src/actions.rs`

We directly use Zed's `gpui::actions!()` macro:

```rust
actions!(editor, [MoveCursorUp, MoveCursorDown, ...Copy, Paste, Undo, Redo]);
actions!(workspace, [Save, SaveAs, Close, ...]);
```

### Gap Analysis: Actions

| Aspect | Zed | Ours | Status |
|--------|-----|------|--------|
| Action macro | `gpui::actions!()` | Same macro | **ALIGNED** |
| Action trait | Full `Action` trait from GPUI | Re-uses GPUI's trait | **ALIGNED** |
| Complex actions | `#[derive(Action)]` with params | Not used yet | Available when needed |
| JSON deserialization | For keymap loading from files | Not used yet | Available via Action derive |
| Registration | Automatic via `register_action!` | Handled by GPUI | **ALIGNED** |

---

## 7. Dispatch Tree

### Zed

**File**: `ref/zed/crates/gpui/src/key_dispatch.rs:71-80`

The `DispatchTree` is the core data structure for routing keyboard events:

```rust
pub(crate) struct DispatchTree {
    node_stack: Vec<DispatchNodeId>,
    context_stack: Vec<KeyContext>,
    view_stack: Vec<EntityId>,
    nodes: Vec<DispatchNode>,
    focusable_node_ids: FxHashMap<FocusId, DispatchNodeId>,
    view_node_ids: FxHashMap<EntityId, DispatchNodeId>,
    keymap: Rc<RefCell<Keymap>>,
    action_registry: Rc<ActionRegistry>,
}
```

Each `DispatchNode` stores:

- `key_listeners: Vec<KeyListener>` -- raw key event listeners
- `action_listeners: Vec<DispatchActionListener>` -- action-specific listeners
- `modifiers_changed_listeners` -- modifier state change listeners
- `context: Option<KeyContext>` -- context for this node
- `focus_id: Option<FocusId>` -- if this node is focusable
- `view_id: Option<EntityId>` -- the view this node belongs to
- `parent: Option<DispatchNodeId>` -- parent in tree

The tree supports:

- `push_node()` / `pop_node()` during element paint
- `reuse_subtree()` for incremental tree updates
- `dispatch_path()` -- root-to-target path
- `focus_path()` -- root-to-focus path
- `focus_contains()` -- parent/child focus checking
- `available_actions()` -- all actions reachable from a node

### Ours

**File**: `crates/pp-editor-events/src/dispatch.rs`

Our dispatch module defines the **types** but not the tree itself:

- `DispatchNodeId(usize)` -- matches Zed
- `DispatchPhase { Capture, Bubble }` -- matches Zed
- `DispatchResult { Handled, HandledAndStopped, NotHandled }` -- different from Zed's DispatchResult
- `ActionRegistration { action_type: TypeId, node_id: DispatchNodeId }` -- metadata only
- `ActionHandler` trait -- custom trait not in Zed

### Gap Analysis: Dispatch Tree

| Aspect | Zed | Ours | Gap |
|--------|-----|------|-----|
| Tree structure | Full `DispatchTree` with nodes, stacks, maps | Types only, no tree implementation | **CRITICAL**: Zed's dispatch tree is built and managed by GPUI Window internally |
| DispatchResult | Contains pending keystrokes, bindings, to_replay | Simple handled/not-handled enum | Different purpose: Zed's is keystroke dispatch result, ours is action handler result |
| Integration point | `Window.next_frame.dispatch_tree` built during paint | Not integrated with GPUI paint | **NOTE**: We don't need to reimplement -- GPUI provides this |

**Important insight**: The `DispatchTree` is an **internal GPUI structure** built automatically during element painting. Our crate should not reimplement it. Instead, we should rely on GPUI's built-in dispatch by registering handlers via `.on_action()`, `.on_key_event()`, etc. Our `DispatchPhase` and related types are for handler APIs, not tree construction.

---

## 8. Focus System

### Zed

Focus in Zed is managed by GPUI:

- `FocusHandle` created via `cx.focus_handle()`
- `.track_focus(&handle)` on elements during render
- `handle.is_focused(window)` for state queries
- `FocusInEvent`, `FocusOutEvent` for notifications
- Focus stored in `Frame.focus: Option<FocusId>`
- Dispatch tree tracks `focusable_node_ids` mapping

### Ours

**File**: `crates/pp-editor-events/src/focus.rs`

We re-export GPUI's core types and add custom tracking:

- Re-exports: `FocusHandle`, `FocusId`, `WeakFocusHandle`
- Custom: `FocusEvent`, `BlurEvent`, `FocusChangeTracker`, `FocusRestorer`, `FocusHistory`

### Gap Analysis: Focus

| Aspect | Zed | Ours | Status |
|--------|-----|------|--------|
| FocusHandle | From GPUI | Re-exported | **ALIGNED** |
| Focus tracking | GPUI Frame + dispatch tree | Custom `FocusChangeTracker` | Ours is supplementary |
| Focus events | `FocusInEvent` / `FocusOutEvent` from GPUI | Custom `FocusEvent` / `BlurEvent` | Parallel to GPUI events |
| Focus restoration | Ad-hoc per modal implementation | `FocusRestorer` with stack | **Enhancement** over Zed |
| Focus history | Not present in GPUI | `FocusHistory` with back navigation | **Enhancement** over Zed |

---

## Summary of Critical Gaps

### Blockers for Interactive Editor Demo

1. **EntityInputHandler implementation**: Must implement the GPUI trait on our editor view for IME to work. Current standalone struct pattern won't integrate with GPUI's platform input pipeline.

2. **Buffer integration**: `replace_text_in_range` and `replace_and_mark_text_in_range` are stubs. Need text buffer write access.

3. **Keystroke prefix replay**: When a multi-stroke sequence fails mid-way, Zed recursively replays the longest matching prefix. Our implementation drops the sequence entirely.

### Architecture Alignment (Already Good)

1. **Hit testing algorithm**: Identical to Zed's.
2. **Action system**: Uses Zed's `gpui::actions!()` macro directly.
3. **HitboxBehavior model**: Identical three-variant enum.
4. **Focus primitives**: Correctly re-exports GPUI's FocusHandle system.
5. **Dispatch tree**: Correctly delegates to GPUI (not reimplementing).

### Enhancements Beyond Zed

1. **FocusRestorer**: Stack-based focus save/restore for modals.
2. **FocusHistory**: Back-navigation through focus history.
3. **Timeout configuration**: Configurable keystroke timeout (Zed uses a fixed constant).
4. **Explicit DragState machine**: Clean state machine vs Zed's inline handler logic.

### Recommended Priorities for Demo

1. Implement `EntityInputHandler` on editor view (bridges IME)
2. Wire `replace_text_in_range` to text buffer
3. Add click count detection for word/line selection
4. Connect `PositionMap` to real layout data from display map
5. Add prefix replay logic to `KeystrokeMatcher`

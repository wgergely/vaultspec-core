---
tags:
  - "#plan"
  - "#editor-demo"
date: 2026-02-05
related:
  - "[[2026-02-05-editor-demo-architecture]]"
  - "[[2026-02-05-editor-demo-research]]"
  - "[[2026-02-05-editor-demo-events-reference]]"
  - "[[2026-02-05-editor-demo-core-reference]]"
  - "[[2026-02-05-editor-demo-rendering-reference]]"
  - "[[2026-02-04-editor-event-handling]]"
---

# Editor Demo Phase 2 Plan: Event Integration

Make input work. Bridge GPUI's platform input system to the editor buffer so users can type text, navigate with the keyboard, click to position the cursor, and select text with the mouse. This phase depends on Phase 1's rendering foundation (hitboxes, EditorLayout, ShapedLine data).

## Proposed Changes

The event handling pipeline is at 70% alignment with Zed ([[2026-02-05-editor-demo-events-reference]] Summary). The hit testing algorithm, action system, and focus primitives are correct. However, two critical blockers prevent any interactive input:

1. **EntityInputHandler is not implemented.** GPUI's platform text input (keyboard, IME) routes through the `EntityInputHandler` trait. Without implementing it on `EditorView`, no keyboard input reaches the editor buffer. The current `EditorInputHandler<P>` in `crates/pp-editor-events/src/ime/handler.rs` is a standalone struct using `Arc<RwLock<...>>` -- it does not implement the GPUI trait and cannot integrate with the entity system ([[2026-02-05-editor-demo-events-reference]] Section 1).

2. **PositionMap is a stub.** `StubPositionMap` in `crates/pp-editor-events/src/position_map.rs` provides fixed-width character mapping. Without connecting it to the actual layout data from Phase 1's `EditorLayout` (which contains `ShapedLine` widths), click-to-position and selection drag cannot work correctly ([[2026-02-05-editor-demo-events-reference]] Section 5).

Additionally, the undo/redo system lacks transaction grouping -- typing "Hello" creates 5 separate undo entries ([[2026-02-05-editor-demo-core-reference]] Section 4). This is a critical UX issue for an interactive demo.

## Tasks

1. **Implement EntityInputHandler on EditorView**

   - Step summary: `.docs/exec/2026-02-05-editor-demo/2026-02-05-editor-demo-phase2-step1.md`
   - Executing sub-agent: standard-executor
   - References: [[2026-02-05-editor-demo-events-reference]] Section 1, [[2026-02-05-editor-demo-architecture]] Phase 2 Task 1

   Sub-steps:
   1. Implement `gpui::EntityInputHandler` trait on `EditorView`. The trait requires methods: `text_for_range`, `selected_text_range`, `marked_text_range`, `unmark_text`, `replace_text_in_range`, `replace_and_mark_text_in_range`, `bounds_for_range`, `character_index_for_point`, and `accepts_text_input`. Each method receives `&mut self, ..., window: &mut Window, cx: &mut Context<Self>`.
   2. Wire `replace_text_in_range` to the editor buffer. When the platform sends text (e.g., a keystroke produces "a"), this method must: (a) resolve the replacement range (None means current selection), (b) delete the selected range if present, (c) insert the text at the cursor position via `EditorState::insert()`, (d) update the cursor position, (e) notify the model for re-render via `cx.notify()`.
   3. Wire `replace_and_mark_text_in_range` for IME composition. This must: (a) track the composition range, (b) replace text in the buffer temporarily, (c) mark the range for underline rendering. Use the existing `CompositionState` from `pp-editor-events` to track the marked range.
   4. Implement `selected_text_range` to return the current cursor position (or selection range) converted to UTF-16 offsets. The conversion from char offsets to UTF-16 offsets requires iterating the buffer text and counting UTF-16 code units.
   5. Implement `text_for_range` to extract text from the buffer for the given UTF-16 range.
   6. Implement `bounds_for_range` to return pixel bounds for the given UTF-16 range, using the `ShapedLine` data from the most recent `EditorLayout`. This requires caching the last `EditorLayout` (or relevant parts of it) so it is accessible outside the Element lifecycle.
   7. Register the input handler in `EditorElement::paint()` using the GPUI bridging pattern: construct `ElementInputHandler::new(view_entity, element_bounds)` (which wraps the `EntityInputHandler` impl into a concrete `InputHandler`), then call `window.handle_input(&focus_handle, element_input_handler, app)`. This requires passing the `Entity<EditorView>` handle and `FocusHandle` into `EditorElement`.
   8. The existing standalone `EditorInputHandler<P>` in `pp-editor-events` is superseded for GPUI integration. It may still be useful for non-GPUI testing. Do not delete.

2. **Connect PositionMap to layout data from prepaint**

   - Step summary: `.docs/exec/2026-02-05-editor-demo/2026-02-05-editor-demo-phase2-step2.md`
   - Executing sub-agent: standard-executor
   - References: [[2026-02-05-editor-demo-events-reference]] Section 5, [[2026-02-05-editor-demo-architecture]] Phase 2 Task 2

   Sub-steps:
   1. Create a `LayoutPositionMap` struct (or similar name) in `pp-editor-main` that implements the `PositionMap` trait from `pp-editor-events`. This struct holds: a reference (or cloned data) to the `Vec<ShapedLine>` from the most recent prepaint, the scroll position, line height, gutter width, and visible row range.
   2. Implement `position_from_point` using ShapedLine width data. For a given pixel point: (a) subtract gutter width and scroll offset, (b) compute the display row from `(y - text_origin.y) / line_height`, (c) for the target row, iterate the `ShapedLine` glyph runs to find which character offset the x-coordinate falls within (using cumulative glyph widths, not fixed char_width).
   3. Implement `point_for_position` using ShapedLine data. For a given (row, column): (a) find the ShapedLine for that row, (b) sum glyph widths up to the column to get the x-coordinate, (c) multiply row by line_height for y.
   4. Implement `bounds_for_range` for multi-line selections and IME candidate positioning.
   5. Cache the `LayoutPositionMap` on `EditorView` (or share via `Arc`) after each prepaint cycle. The position map must be refreshed every time `EditorLayout` is recomputed.
   6. Register mouse event handlers on `EditorElement` in `paint()`: `on_mouse_down`, `on_mouse_move`, `on_mouse_up`. These handlers use the `LayoutPositionMap` to convert pixel coordinates to buffer positions and update the cursor/selection state on `EditorModel`.

3. **Add click count detection (word/line select)**

   - Step summary: `.docs/exec/2026-02-05-editor-demo/2026-02-05-editor-demo-phase2-step3.md`
   - Executing sub-agent: standard-executor
   - References: [[2026-02-05-editor-demo-events-reference]] Section 5, [[2026-02-05-editor-demo-architecture]] Phase 2 Task 3

   Sub-steps:
   1. Add click count tracking to `EditorView` (or a dedicated `ClickTracker` struct): store the last click time, last click position, and current click count.
   2. On `mouse_down`: if the new click is within a threshold distance (e.g., 4px) of the last click and within a threshold time (e.g., 500ms), increment click count. Otherwise reset to 1.
   3. For click_count == 1: position cursor at the clicked buffer position (current behavior).
   4. For click_count == 2 (double-click): select the word at the clicked position. Word boundaries are defined by Unicode word segmentation or a simpler whitespace/punctuation boundary check. Update `Cursor::selection` to span the word.
   5. For click_count == 3 (triple-click): select the entire line at the clicked position. Update `Cursor::selection` to span from line start to line end (including newline).
   6. Connect the click count to the `SelectionDragState` in `pp-editor-events` so that drag-from-double-click extends the selection by words, and drag-from-triple-click extends by lines.

4. **Add transaction grouping to undo/redo**

   - Step summary: `.docs/exec/2026-02-05-editor-demo/2026-02-05-editor-demo-phase2-step4.md`
   - Executing sub-agent: standard-executor
   - References: [[2026-02-05-editor-demo-core-reference]] Section 4, [[2026-02-05-editor-demo-architecture]] Phase 2 Task 4

   Sub-steps:
   1. Add a `group_interval: Duration` field to `History` in `crates/pp-editor-core/src/history.rs`. Default to `Duration::from_millis(300)`.
   2. Add a `last_edit_time: Option<Instant>` field to `History`.
   3. Modify `History::push()`: when a new operation arrives within `group_interval` of `last_edit_time`, merge it with the last operation on the undo stack (create a `Batch` if the last op is not already a `Batch`, or append to the existing `Batch`). When outside the interval, push as a new entry.
   4. Add a `CursorState` snapshot (position + selection) to each undo stack entry. Define a wrapper: `struct HistoryEntry { op: Operation, cursor_before: CursorSnapshot, cursor_after: CursorSnapshot }` where `CursorSnapshot` captures the cursor position and optional selection range.
   5. Modify `History::undo()` to return both the inverted operation and the `cursor_before` snapshot.
   6. Modify `History::redo()` to return both the operation and the `cursor_after` snapshot.
   7. In `EditorState::undo()` and `EditorState::redo()`, restore the cursor state from the history entry after applying the operation.
   8. Add a `force_new_transaction()` method to `History` that resets `last_edit_time` to force the next edit into a new undo group. Call this on explicit boundary actions (e.g., cursor movement, paste, newline insertion).

## Parallelization

- **Task 1 (EntityInputHandler) and Task 4 (transaction grouping) can proceed in parallel.** Task 1 operates on `pp-editor-main` (GPUI integration layer) while Task 4 operates on `pp-editor-core` (framework-agnostic core). They share no files.
- **Task 2 (PositionMap) depends on Phase 1 completion** (needs `EditorLayout` with `ShapedLine` data). It can proceed in parallel with Task 4.
- **Task 3 (click count) depends on Task 2** (needs `PositionMap` for click-to-position) and partially on Task 1 (needs mouse handlers registered on EditorElement).
- **Task 1 should be tested against Task 4** at integration time: typing text should produce grouped undo entries via the EntityInputHandler path.

Execution order: `(1 | 4) -> 2 -> 3` (with integration testing after all four)

## Verification

### Success Criteria

1. **Keyboard input works.** Typing on the keyboard inserts characters into the buffer at the cursor position. The editor re-renders with the new text after each keystroke. Verified by running `cargo run --example demo -p pp-editor-main` and typing.
2. **Backspace and Delete work.** Pressing Backspace removes the character before the cursor. Delete removes the character after.
3. **Arrow key navigation works.** Up/Down/Left/Right move the cursor. Home/End move to line start/end. Verified by cursor position after key presses.
4. **Click-to-position works.** Clicking in the text area positions the cursor at the correct character. Clicking at the end of a short line positions the cursor at line end, not beyond it.
5. **Mouse selection works.** Click-and-drag selects text. The selection highlight renders correctly. Releasing the mouse button commits the selection.
6. **Double-click selects word.** Double-clicking on a word selects the entire word.
7. **Triple-click selects line.** Triple-clicking selects the entire line.
8. **Undo groups keystrokes.** Typing "Hello" quickly (within 300ms per keystroke) then pressing Ctrl+Z undoes the entire word in one step, not character by character.
9. **Undo restores cursor position.** After undoing, the cursor returns to where it was before the edit.
10. **IME composition works.** On platforms with IME support (macOS, Windows), starting an IME composition shows underlined composition text. Committing the composition inserts the final text. Cancelling removes the composition text.
11. **`cargo check --all-targets` passes** for `pp-editor-main`, `pp-editor-events`, and `pp-editor-core`.

### Verification Method

- Run `cargo test -p pp-editor-core` to verify transaction grouping and cursor restore logic.
- Run `cargo test -p pp-editor-main` to verify no regressions.
- Run `cargo run --example demo -p pp-editor-main` for interactive verification of typing, clicking, selection, and undo.
- IME verification requires platform-specific testing (enable a CJK input method and attempt composition). This may not be automatable -- document the manual test procedure.
- Unit tests should cover: (a) transaction grouping merges within interval, (b) transaction grouping splits across interval, (c) cursor snapshot save/restore on undo/redo, (d) UTF-16 offset conversion correctness.

---
tags:
  - "#reference"
  - "#editor-demo"
date: 2026-02-06
related:
  - "[[2026-02-05-editor-demo-phase2-plan]]"
  - "[[2026-02-05-editor-demo-events-reference]]"
  - "[[2026-02-05-editor-demo-core-reference]]"
  - "[[2026-02-05-editor-demo-architecture]]"
---

# Editor Demo Reference: Phase 2 Safety Audit

Safety audit of Phase 2 (Event Integration) code changes across 4 commits:

- `4d4d6d2` -- Transaction grouping (pp-editor-core)
- `3057c87` -- EntityInputHandler (pp-editor-main)
- `eb5af85` -- LayoutPositionMap (pp-editor-main)
- `6e0a117` -- Click count detection (pp-editor-main)

## Findings

### 1. BLOCKING: `.expect()` in Production Code

**File:** `crates/pp-editor-core/src/history.rs:189`

```rust
let last = self.undo_stack.last_mut().expect("checked non-empty above");
```

**Severity:** BLOCKING -- Violates No-Crash Policy.

The guard condition at line 183-185 checks `!self.undo_stack.is_empty()`, making this logically unreachable. However, the project mandates zero `expect()` / `unwrap()` in production code. Clippy with `-D clippy::expect-used` correctly flags this.

**Fix:** Replace with a safe pattern:

```rust
let Some(last) = self.undo_stack.last_mut() else { return; };
```

This is functionally identical (the else branch is unreachable) but satisfies the no-panic contract.

### 2. Direct Indexing in `LayoutPositionMap` (Guarded -- Non-blocking)

**File:** `crates/pp-editor-main/src/position_map.rs:159-160`

```rust
let line = &self.lines[display_line];
let origin = &self.line_origins[display_line];
```

**File:** `crates/pp-editor-main/src/position_map.rs:183-184`

```rust
let line = &self.lines[idx];
let origin = &self.line_origins[idx];
```

**Assessment:** Non-blocking but worth documenting. The first pair (lines 159-160) is protected by the empty check at line 154 (`if self.lines.is_empty() { return Position::zero(); }`) and by `display_line_for_y()` which returns indices within `0..lines.len()`. The second pair (lines 183-184) is protected by `self.lines.iter().position()` returning `Some(idx)`. Both are sound.

**Recommendation:** Consider adding `.get()` with fallback for defense-in-depth, but this is NOT blocking.

### 3. Memory Safety & Ownership -- PASS

- `LayoutPositionMap` is correctly wrapped in `Arc<Self>` from `from_layout()` (line 77-100). The Arc is shared between paint-phase mouse handlers via closures.
- `AtomicU8` for `select_mode` (editor_element.rs:665) is appropriate for cross-closure state sharing. Uses `Ordering::Relaxed` which is sufficient since the mode is only accessed from the same thread (GPUI event loop).
- `ShapedLine` data is cloned into `PositionMapLine` during construction, avoiding lifetime entanglement with the `EditorLayout` struct.
- `EditorView` implements `EntityInputHandler` borrowing the model via `self.model.read(cx)` and `self.model.update(cx, ...)` -- correct GPUI entity borrowing patterns.

### 4. UTF-16 Conversion Correctness -- PASS

**File:** `crates/pp-editor-main/src/editor_view.rs:532-546`

- `char_offset_to_utf16()` correctly counts UTF-16 code units via `c.len_utf16()`.
- `utf16_offset_to_char()` correctly iterates chars, accumulating UTF-16 lengths.
- Both handle edge cases: empty strings, positions past end (returns `text.chars().count()`).
- `text_for_range()` clamps both start and end to `total_chars` and reports `adjusted_range` if clamping occurs. Correct per GPUI contract.

### 5. EntityInputHandler Implementation -- PASS with Notes

**File:** `crates/pp-editor-main/src/editor_view.rs:550-741`

- `replace_text_in_range()` (lines 616-642): Correctly handles three cases: explicit range, current selection, and cursor insertion. Calls `cx.notify()` after mutation.
- `replace_and_mark_text_in_range()` (lines 644-656): Delegates to `replace_text_in_range()` with a comment explaining IME composition is deferred. Acceptable for the demo phase.
- `selected_text_range()` (lines 580-601): Returns `UTF16Selection` with correct reversed flag computation (`sel.anchor() > sel.head()`).
- `bounds_for_range()` (lines 658-701): Uses layout fallback with `char_position()` and `measure_line()`. Returns correct pixel bounds for cursor positioning.
- `character_index_for_point()` (lines 703-740): Uses `layout.index_at_position()` with `unwrap_or(line_text.chars().count())` -- safe fallback.

**Note:** `marked_text_range()` and `unmark_text()` return `None` / no-op respectively. This is documented and acceptable for the current phase.

### 6. Mouse Event Handlers -- PASS

**File:** `crates/pp-editor-main/src/editor_element.rs:659-779`

- `paint_mouse_listeners()` follows Zed's pattern of registering `on_mouse_event()` during paint phase.
- Click count handling correctly covers 1 (char), 2 (word), 3 (line), 4+ (select all).
- Gutter clicks always treated as line select (`click_count = 3`). Matches Zed pattern.
- `select_mode` capped at 4 via `.min(4)` before `as u8` cast -- prevents overflow.
- `MouseUpEvent` resets `select_mode` to 1 -- correct cleanup.
- Shift+click properly extends selection respecting the current mode.

### 7. Word/Line Selection Helpers -- PASS with Note

**File:** `crates/pp-editor-main/src/editor_element.rs:785-872`

- `find_word_start()` and `find_word_end()` use `buffer.char_at(idx).unwrap_or(' ')` -- safe fallback treating out-of-bounds as non-word character (space).
- `extend_to_word()` and `extend_to_line()` correctly preserve the selection anchor and extend to the appropriate boundary based on drag direction.
- `select_word_at()` and `select_line_at()` use `buffer_and_cursor_mut()` to split the borrow -- correct ownership pattern.

**Note:** The `is_word_char()` implementation (alphanumeric + underscore) is simplistic compared to Unicode word segmentation. Acceptable for the demo phase.

### 8. Transaction Grouping -- PASS (conditional on Fix #1)

**File:** `crates/pp-editor-core/src/history.rs:136-278`

- Time-based merging with 300ms default interval. Uses `Instant::now()` and `duration_since()` -- correct monotonic clock usage.
- `push_grouped()` merges into `Batch` operations. Preserves `cursor_before` from the first entry and `cursor_after` from the last -- correct for undo/redo cursor restore.
- `force_new_transaction()` resets `last_edit_time` to `None` -- clean boundary mechanism.
- `undo_with_cursor()` and `redo_with_cursor()` correctly invert operations and restore cursor snapshots.
- Backward-compatible: `push()` and `undo()` still work without cursor info.

**Conditional:** The `.expect()` at line 189 must be replaced (see Finding #1).

### 9. EditorState Integration -- PASS

**File:** `crates/pp-editor-core/src/state.rs`

- `cursor_snapshot()` (lines 175-182) and `restore_cursor()` (lines 185-192) correctly capture and restore cursor + selection state.
- `insert()` (lines 205-228) and `insert_char()` (lines 231-247) both use `push_grouped()` with proper cursor snapshots.
- Multi-character inserts correctly force new transactions (lines 207-209, 225-227).
- `delete_backward()`, `delete_forward()`, and `delete_selection()` all capture cursor snapshots and use `push_grouped()`.
- `insert_newline()` forces transaction boundaries before and after -- correct behavior for discrete undo entries.

### 10. Input Handler Registration -- PASS

**File:** `crates/pp-editor-main/src/editor_element.rs:549-572`

- Input handler registered in `paint()` phase using `window.handle_input()` with `ElementInputHandler::new(bounds, view.clone())` -- correct GPUI pattern.
- Guard `if let (Some(view), Some(focus_handle))` at line 550 prevents crashes in test mode where view/focus_handle are None.
- `LayoutPositionMap` built from layout data in paint phase and passed to mouse listeners via `Arc` -- correct ownership.

### 11. `unsafe` Code Audit -- PASS

- `crates/pp-editor-main/src/lib.rs:2` declares `#![forbid(unsafe_code)]` -- no unsafe code possible in pp-editor-main.
- `crates/pp-editor-core/src/layout/cosmic.rs:186,333` has two `unsafe` blocks with `#[allow(unsafe_code)]` for `std::mem::transmute` on font IDs. These are pre-existing and outside Phase 2 scope.

## Summary

| Domain | Verdict | Notes |
|--------|---------|-------|
| Memory Safety & Ownership | PASS | Arc sharing, entity borrowing, borrow splitting all correct |
| No-Crash Policy | **BLOCKED** | `expect()` at history.rs:189 must be replaced |
| Error Integrity | PASS | Fallbacks used throughout (unwrap_or, let-else, Option returns) |
| Async & Concurrency | N/A | No async code in Phase 2 changes |
| Unsafe Audit | PASS | forbid(unsafe_code) in pp-editor-main; pre-existing unsafe in cosmic.rs only |
| Architectural Alignment | PASS | Matches Zed patterns: paint-phase handlers, EntityInputHandler, PositionMap |
| Plan Compliance | PASS | All 4 tasks implemented per plan specification |

**Overall: CONDITIONALLY APPROVED -- pending single fix at history.rs:189.**

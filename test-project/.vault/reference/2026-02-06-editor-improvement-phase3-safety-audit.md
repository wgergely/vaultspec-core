---
tags:
  - "#reference"
  - "#editor-improvement"
date: 2026-02-06
related:
  - "[[2026-02-06-editor-improvement-plan]]"
  - "[[2026-02-06-incremental-layout-engine-design-adr]]"
  - "[[2026-02-06-editor-audit-reference]]"
---

# Phase 3: UI Feature Completion - Safety & Correctness Audit

This document tracks the safety and correctness audit for Phase 3 of the Editor Improvement Plan. The audit covers all code changes made during Phase 3 implementation across `pp-editor-main`, `pp-editor-core`, and `pp-editor-events`.

## Audit Standards

- **Edition**: 2024, rust-version 1.93
- **Clippy Lints**: `unwrap_used = deny`, `expect_used = deny`, `panic = deny`, `unsafe_code = deny`
- **Visibility**: `pub(crate)` default
- **Error Handling**: `thiserror` for libraries, `anyhow` for applications
- **No-Crash Policy**: Zero `unwrap()`, `expect()`, `panic!()`, `todo!()`, `unimplemented!()` in production code paths

## Pre-Phase 3 Baseline

The following pre-existing issues were identified before Phase 3 work began. These are **NOT** regressions introduced by Phase 3 but are tracked for context.

### Pre-existing: `pp-editor-main/src` Production Code

| File | Line | Symbol | Severity | Note |
|------|------|--------|----------|------|
| `editor_element.rs` | (tests only) | `.unwrap()` x4, `.expect()` x4 | NB | Test-only, acceptable |
| `gutter.rs` | 358 | `panic!()` | NB | Test-only, acceptable |
| `text_renderer.rs` | 461, 465 | `.unwrap()` x2 | NB | Test-only, acceptable |

**Verdict**: `pp-editor-main/src` has NO pre-existing safety violations in production code. All `unwrap`/`expect`/`panic` instances are within `#[cfg(test)]` blocks.

### Pre-existing: `pp-editor-core/src` Production Code

| File | Line | Symbol | Severity | Note |
|------|------|--------|----------|------|
| `layout/cosmic.rs` | 198, 348 | `unsafe { transmute }` x2 | **B** | Has `// SAFETY:` comments documenting invariants. Pre-existing, not Phase 3. |
| `state.rs` | 861 | `.expect()` | NB | Test-only |
| `text.rs` | 397, 401, 406 | `.expect()` x3 | NB | Test-only (fuzzing) |
| Various test files | Multiple | `.unwrap()`, `panic!()` | NB | Test-only, acceptable |

**Verdict**: `pp-editor-core/src` has 2 pre-existing `unsafe` blocks in `layout/cosmic.rs` with documented SAFETY comments. No other production-path safety violations.

### Pre-existing: `pp-editor-events/src` Production Code

| File | Line | Symbol | Severity | Note |
|------|------|--------|----------|------|
| `ime/rendering.rs` | 249 | `.expect()` | NB | Test-only |
| `ime/candidate.rs` | 164, 191 | `.expect()` | NB | Test-only |

**Verdict**: `pp-editor-events/src` has NO pre-existing safety violations in production code. Lock poisoning is handled gracefully with `tracing::error!` and fallback returns.

### Pre-existing Architecture Notes

1. **IME Handler** (`pp-editor-events/src/ime/handler.rs`):
   - `replace_text_in_range` is a stub returning `Err(anyhow!("not implemented"))` - correct approach.
   - `character_index_for_point` has a stub comment: "assume character index = column" - needs proper UTF-16 conversion.
   - Lock poisoning handled correctly everywhere via `match .read()/.write()` with `Err` branches.

2. **BlockMap** (`pp-editor-core/src/display_map/block_map.rs`):
   - Well-structured SumTree-based implementation.
   - No `unwrap`/`expect`/`panic` in production code.
   - Thorough test coverage (14 tests).

3. **FoldingSystem** (`pp-editor-main/src/folding.rs`):
   - Clean implementation with `BTreeMap`-based fold storage.
   - `saturating_sub` used correctly for boundary cases.
   - `visual_to_buffer_line` and `buffer_to_visual_line` are O(n) - acceptable for current scope but may need optimization later.

4. **Gutter** (`pp-editor-main/src/gutter.rs`):
   - Command-based rendering (deprecated note present).
   - `calculate_gutter_width` uses `log10().floor() as usize` - safe because guarded by `if line_count == 0 { 1 }`.
   - Line number approximation uses `text.len() as f32 * Size::SM.px()` - rough but acceptable.

5. **Core Folding** (`pp-editor-core/src/folding.rs` + `folding/markdown.rs`):
   - Markdown fold detection uses `MarkdownParser` spans.
   - No safety issues identified.

---

## Phase 3 Step Reviews

### Step 1: IME Composition Tracking

**Status**: REVIEWED (working tree, pre-commit)
**Reviewer**: code-reviewer
**Files Changed**: `editor_view.rs`, `editor_element.rs`, `editor_handle.rs`, `editor_model.rs`, `position_map.rs`

#### Safety Scan

| File | Symbol | Classification | Detail |
|------|--------|----------------|--------|
| `editor_view.rs:685` | `.unwrap_or_else(...)` | OK | Safe fallback pattern; provides cursor position default if `selection()` returns None despite `has_selection()` true |
| `editor_view.rs:155` | `.unwrap_or(0.0)` | OK | Pre-existing safe default |
| `editor_view.rs:814` | `.unwrap_or(...)` | OK | Pre-existing safe default |
| All production code | No `.unwrap()`, `.expect()`, `panic!()`, `todo!()`, `unsafe` | PASS | |

**Zero new prohibited symbols introduced in production code.**

#### BLOCKING Findings

**B-1: Potential panic in `compute_composition_underlines` via stale composition range**

- **File**: `editor_element.rs:274-275`
- **Code**:

  ```rust
  let comp_start_line = buffer.char_to_line(comp_start);
  let comp_end_line = buffer.char_to_line(comp_end.saturating_sub(1).max(comp_start));
  ```

- **Risk**: `buffer.char_to_line()` delegates to Ropey's `char_to_byte_idx()` which panics if the char index exceeds `buffer.len_chars()`. If the IME composition range becomes stale (e.g., buffer modified via undo/redo, external paste, or action dispatch without clearing `ime_composition`), the composition range could point past the end of the buffer, causing a panic.
- **Likelihood**: LOW in normal IME flow (platform always calls `unmark_text` or `replace_text_in_range` first), but MEDIUM during edge cases (keyboard shortcut undo during composition, programmatic buffer modification).
- **Fix**: Add bounds clamping before the Ropey calls:

  ```rust
  let buf_len = buffer.len_chars();
  let comp_start = composition.range.start.min(buf_len);
  let comp_end = composition.range.end.min(buf_len);
  ```

  Alternatively, clear `ime_composition` in `EditorModel::dispatch_action` for any buffer-modifying action.

#### NON-BLOCKING Findings

**NB-1: `ImeComposition.range` field is `pub` (visibility)**

- **File**: `editor_view.rs:32`
- **Detail**: `pub range: Range<usize>` should be `pub(crate)` per project standards. The struct itself is `pub` but the field doesn't need to be externally accessible.

**NB-2: Composition range not invalidated on non-IME buffer mutations**

- **Detail**: `EditorView::ime_composition` is only cleared via `unmark_text` and `replace_text_in_range`. If `EditorModel::dispatch_action` modifies the buffer (e.g., Undo, Redo, DeleteBackward via keyboard), the composition range is NOT cleared. In practice, the platform IME protocol prevents this, but it's fragile.
- **Recommendation**: Add `self.ime_composition = None;` at the start of any non-IME buffer mutation path, or expose a `clear_composition()` method from EditorView that EditorModel can call.

**NB-3: `new_selected_range` offset interpretation may be incorrect**

- **File**: `editor_view.rs:715-723`
- **Detail**: The `new_selected_range` parameter from the platform is typically relative to the composition text itself, not the full document. The current code calls `utf16_offset_to_char(&text, sel_range.start)` using the full document text, which interprets the offset as an absolute document position. If the platform provides composition-relative offsets (as macOS does), the cursor will be positioned incorrectly.
- **Recommendation**: Verify platform behavior. If composition-relative, the calculation should be:

  ```rust
  let sel_start_char = sel_range.start; // Already a char offset relative to composition
  ```

  This depends on GPUI's contract for `new_selected_range`. Verify against GPUI documentation or Zed's implementation.

**NB-4: `editor_handle.rs` changes are formatting-only**

- **Detail**: All changes in `editor_handle.rs` are trailing whitespace removal on `#[must_use]` lines. No functional changes. Acceptable.

**NB-5: `editor_model.rs` changes are formatting-only**

- **Detail**: `dispatch_action` import list reformatted for readability. `#[must_use]` trailing whitespace removed. No functional changes. Acceptable.

**NB-6: `position_map.rs` changes are formatting-only**

- **Detail**: `#[must_use]` trailing whitespace removed. No functional changes. Acceptable.

#### Correctness Assessment

1. **`ImeComposition` struct**: Correct. Simple char-offset range tracking. `Clone`, `PartialEq`, `Eq`, `Debug` derives are appropriate.

2. **`marked_text_range` implementation**: Correct. Uses `char_offset_to_utf16` for proper conversion. Returns `None` when no composition is active.

3. **`unmark_text` implementation**: Correct. Simply clears `self.ime_composition = None`.

4. **`replace_and_mark_text_in_range` implementation**: Mostly correct. The fallback chain (range_utf16 -> composition -> selection -> cursor) is well-structured. The `unwrap_or_else` on the selection path is a safe defensive pattern.

5. **`replace_text_in_range` clearing composition**: Correct. A committed text replacement clears any active composition.

6. **`compute_composition_underlines`**: Good implementation. Handles multi-line compositions, converts char columns to byte offsets for ShapedLine, and uses `max(px(0.0))` to prevent negative widths. The bounds-checking on array indices (line 284-287) is thorough.

7. **Paint code** (`editor_element.rs` paint phase): Correct. Uses `fill` with foreground color for underline rendering.

8. **Test coverage**: 7 new tests for `ImeComposition`. Tests cover struct creation, cloning, empty ranges, CJK offsets, UTF-16 roundtrip, and debug display. Good coverage for the data type, but no integration tests for the full `replace_and_mark_text_in_range` flow (would require GPUI test harness).

#### Architecture Alignment

- Aligns with Phase 3 Step 1 plan: IME composition tracking, marked text range, composition underline rendering.
- Does NOT yet implement IME candidate window positioning (planned but deferred - acceptable).
- The `ImeComposition` struct in `editor_view.rs` is simpler than the `CompositionState`/`CompositionRange` in `pp-editor-events/src/ime/`. There may be duplication concern, but the `pp-editor-events` version uses `Arc<RwLock>` for thread safety while the `editor_view` version is single-threaded GPUI. This is an acceptable architectural divergence.

### Step 2: Custom Block Layout Sync with BlockMap

**Status**: REVIEWED
**Reviewer**: code-reviewer
**Commits**: `43195b0` (feat), `c0d5ec5` (docs)
**Files Changed**: `block_map.rs` (+28 lines), `editor_view.rs` (+18/-12 lines)

#### Safety Scan

| File | Symbol | Classification | Detail |
|------|--------|----------------|--------|
| `block_map.rs` | (all production + tests) | PASS | Zero unwrap/expect/panic/unsafe in new production code |
| `editor_view.rs` | (all production) | PASS | Zero unwrap/expect/panic/unsafe in new production code |

**Zero new prohibited symbols introduced in production code.**

#### BLOCKING Findings

None new from Step 2. **B-1 from Step 1 remains unfixed** (`editor_element.rs:274-275`).

#### NON-BLOCKING Findings

**NB-7: `block_height()` is O(n) linear scan**

- **File**: `block_map.rs:352-368`
- **Detail**: Iterates the entire SumTree via cursor to find a block by ID. O(n) in tree item count. Called once per visible block during `prepare_render_items_static`. Acceptable for typical block counts (<100). Future optimization could add a `HashMap<BlockId, u32>` side-index.

**NB-8: Division by zero produces u32::MAX block height**

- **File**: `editor_view.rs:514-515`
- **Code**: `(f32::from(actual_size.height) / line_height).ceil().max(1.0) as u32`
- **Detail**: If `line_height` is 0.0, division produces `f32::INFINITY`, `as u32` saturates to `u32::MAX`. Won't crash but produces nonsensical height. Extremely unlikely (font size defaults are non-zero).
- **Recommendation**: Guard with `if line_height > 0.0 { ... } else { 1 }`.

#### Correctness Assessment

1. **`block_height()` method**: Correct. Iterates SumTree, matches both `Block` and `Replace` variants by ID. Returns `None` for unknown IDs.

2. **Height comparison and deferred resize**: Correct pattern. Height measured in display-row units (`ceil().max(1.0) as u32`). `HashMap` deduplicates multiple resize events for same block.

3. **Batch resize via `cx.defer`**: Correct. Deferred execution avoids re-entrancy during render. `resize_blocks` -> `resize_batch` performs a single SumTree rebuild. `update_layout()` called only when at least one block actually changed.

4. **Previous TODO resolved**: Old `// TODO: Store original height in DisplayMap correctly` and `// We'll add this logic once we have a way to query current block height from map.` now resolved with `block_height()` query.

5. **Test coverage**: 1 new test `test_block_height_query` covering Above, Replace, unknown ID, and post-resize queries.

#### Architecture Alignment

- Aligns with Phase 3 Step 2 plan: block layout synchronization using BlockMap.
- Aligns with ADR: uses SumTree-based BlockMap with batch resize.
- Follows Zed pattern of deferred layout feedback (measure during paint, resize deferred).

### Step 3: Editor Gutter Rendering

**Status**: REVIEWED
**Reviewer**: code-reviewer
**Commits**: `0cc4f65` (feat), `29fe3aa` (docs)
**Files Changed**: `editor_element.rs` (+154 lines), `gutter.rs` (+231 lines), `editor_model.rs` (+34 lines), `editor_view.rs` (+6/-1 lines), `lib.rs` (+5/-2 lines), `editor_handle.rs` (formatting), `position_map.rs` (formatting)

#### Safety Scan

| File | Symbol | Classification | Detail |
|------|--------|----------------|--------|
| `editor_element.rs` (new production: `compute_gutter_decorations`, `paint_gutter_decorations`, current line highlight) | Zero unwrap/expect/panic/unsafe/todo | PASS | Bounds-checked array access via `.get()` and length guard |
| `editor_element.rs:287-293` | B-1 unchanged | **B** | Pre-existing from Step 1, NOT fixed in this commit |
| `gutter.rs` (new production, lines 13-102) | Zero unwrap/expect/panic/unsafe/todo | PASS | All new types and methods are clean |
| `gutter.rs:451` | `panic!()` | NB | Test-only (pre-existing), acceptable |
| `editor_model.rs` | Zero unwrap/expect/panic/unsafe/todo | PASS | New accessors are clean |
| `editor_view.rs` | Zero unwrap/expect/panic/unsafe/todo | PASS | Clone + pass-through only |
| `lib.rs` | Re-exports only | PASS | |
| `editor_handle.rs` | Formatting only | PASS | |
| `position_map.rs` | Formatting only | PASS | |

**Zero new prohibited symbols introduced in production code.**

#### BLOCKING Findings

None new from Step 3. **B-1 from Step 1 remains unfixed** (`editor_element.rs:287-293` -- composition range passed to `buffer.char_to_line()` without bounds clamping). **Flagged for the 5th time.**

#### NON-BLOCKING Findings

**NB-9: `GutterDecoration` types are `pub` and re-exported (intentional)**

- **File**: `gutter.rs:14-101`, `lib.rs:92-94`
- **Detail**: `DiagnosticSeverity`, `GutterDecoration`, `GutterDecorations` are `pub` and re-exported from `lib.rs`. Intentional for public API. Acceptable.

**NB-10: `GutterDecoration::Custom` label field length not enforced**

- **File**: `gutter.rs:43-44`
- **Detail**: `label: Option<String>` documented as "1-2 chars" but unbounded. No crash risk, rendering concern only.

**NB-12: Hardcoded colors in `paint_gutter_decorations`**

- **File**: `editor_element.rs:838, 856-860`
- **Detail**: Breakpoint color and diagnostic severity colors are hardcoded `Rgba` literals rather than sourced from the theme. Only `DiagnosticSeverity::Hint` uses the theme. Should eventually move to `EditorTheme.gutter` for consistency. No safety impact.

**NB-13: `decoration.clone()` in inner loop**

- **File**: `editor_element.rs:384`
- **Detail**: Each `GutterDecoration` is `.clone()`d when constructing `PositionedGutterDecoration`. For `Custom` variant with `label: Some(String)`, this allocates. Acceptable for typical decoration counts (<10 visible).

#### Correctness Assessment

1. **`PositionedGutterDecoration`** (`editor_element.rs:94-103`): Correct. Pixel-space center + radius + decoration data. `pub(crate)` visibility. Derives `Debug, Clone`.
2. **`compute_gutter_decorations`** (`editor_element.rs:352-390`): Correct and safe. Early return on empty. Bounds check `idx >= line_number_origins.len()` at line 372 prevents OOB. Uses `.get(row)` returning `&[]` for missing lines.
3. **Current line highlight** (`editor_element.rs:661-677`): Correct and safe. `if let Some` guards on `current_line` and `.get(idx)`. Uses `break` after finding match.
4. **`paint_gutter_decorations`** (`editor_element.rs:824-876`): Correct and safe. Iterates pre-computed items, no indexing. Exhaustive `match` over all 3 variants. GPUI quad/fill/outline primitives.
5. **`EditorModel` accessors** (`editor_model.rs:252-263`): Correct. `gutter_decorations()`, `gutter_decorations_mut()`, `add_gutter_decoration()` all safe. Resolves NB-11 from working-tree review.
6. **`EditorView::render`** (`editor_view.rs`): Correct. Clones decorations from model, passes to `EditorElement::new()`.
7. **`lib.rs` re-exports**: Correct. Public API surface updated.
8. **Test coverage**: 14 new tests in `gutter.rs` covering severity equality, all decoration variants, CRUD operations, ordered iteration, cloning. Good coverage.

#### Architecture Alignment

- Aligns with Phase 3 Step 3 plan: gutter rendering with decorations, current line highlight.
- Follows 3-phase Element lifecycle: decorations computed in `prepaint()`, painted in `paint()`.
- `BTreeMap`-based storage ensures ordered iteration during paint pass.
- Types re-exported from `lib.rs` for public API access.
- Decoration painting uses GPUI quad/fill/outline primitives consistent with existing rendering code.

### Step 4: Code Folding

**Status**: REVIEWED
**Reviewer**: code-reviewer
**Commits**: `baa1f30`
**Files Changed**: `folding.rs` (+373 lines), `editor_element.rs` (+189 lines), `editor_model.rs` (+57 lines), `editor_view.rs` (+17 lines), `fold_map.rs` (+89 lines)

#### Safety Scan

| File | Symbol | Classification | Detail |
|------|--------|----------------|--------|
| `folding.rs` (all new production code) | Zero unwrap/expect/panic/unsafe/todo | PASS | |
| `editor_element.rs` (new: `FoldIndicator`, `compute_fold_indicators`, `paint_fold_indicators`) | Zero unwrap/expect/panic/unsafe/todo | PASS | Bounds-checked via `.get()` |
| `editor_element.rs:297-299` | B-1 FIX CONFIRMED | **RESOLVED** | `buf_len = buffer.len_chars(); comp_start.min(buf_len); comp_end.min(buf_len)` |
| `editor_model.rs` (new fold methods) | Zero unwrap/expect/panic/unsafe/todo | PASS | |
| `editor_view.rs` (RenderLine fold state) | Zero unwrap/expect/panic/unsafe/todo | PASS | |
| `fold_map.rs` (new: `unfold`, `unfold_all`) | Zero unwrap/expect/panic/unsafe/todo | PASS | |

**Zero new prohibited symbols introduced in production code.**

**B-1 STATUS: RESOLVED.** The bounds clamping fix is confirmed at `editor_element.rs:297-299`:

```rust
let buf_len = buffer.len_chars();
let comp_start = composition.range.start.min(buf_len);
let comp_end = composition.range.end.min(buf_len);
```

#### BLOCKING Findings

None. B-1 is now resolved.

#### NON-BLOCKING Findings

**NB-14: `detect_indentation_folds` is O(n^2) in worst case**

- **File**: `folding.rs:170-212`
- **Detail**: For each line, looks ahead through all subsequent lines. Worst case (flat indentation with gradual increase) is O(n^2). Acceptable for current scope (markdown files typically <10k lines), but may need optimization for large files.
- **Severity**: LOW.

**NB-15: `sync_to_fold_map` resets and reapplies all folds**

- **File**: `folding.rs:222-237`
- **Detail**: Calls `fold_map.reset(total_rows)` then re-applies every collapsed fold. This is O(f * n) where f is fold count and n is tree size. An incremental approach (diff-based) would be more efficient but is acceptable for the current number of folds.
- **Severity**: LOW.

**NB-16: `FoldMap::unfold` builds intermediate tree then merges**

- **File**: `fold_map.rs:192-278`
- **Detail**: Two-pass approach: first replaces Folded items with Neutral, then merges adjacent Neutral items in a second pass. Could be done in a single pass. No safety concern, just performance.
- **Severity**: LOW.

#### Correctness Assessment

1. **`FoldingSystem` new methods**: Correct.
   - `fold_at/unfold_at`: Uses `get_mut` on BTreeMap -- returns None for missing keys, no crash.
   - `fold_all/unfold_all`: Iterates all values -- safe.
   - `fold_at_line`: Checks start line first, then scans for containing fold -- O(n) but correct.
   - `set_folds`: Guards `fold.start < fold.end` before insert -- rejects invalid ranges.
   - `detect_indentation_folds`: Handles blank lines correctly (skipped, don't break folds). Only creates folds where `end > start`.
   - `sync_to_fold_map`: Correctly maps FoldRegion (start, end] hide range to FoldMap (start+1, end+1) row range.

2. **`FoldMap::unfold`** (`fold_map.rs:192-278`): Correct. Checks overlap between unfold range and existing Folded items. Converts overlapping Folded to Neutral. Merges adjacent Neutral items. Guard `start_row >= end_row` for early return.

3. **`FoldMap::unfold_all`**: Correct. Replaces entire tree with single Neutral item spanning all input rows.

4. **`FoldIndicator` struct and rendering**: Correct. `compute_fold_indicators` uses `.get()` for bounds-safe access. Only creates indicators for lines with `has_fold == true`. `paint_fold_indicators` uses filled quad (collapsed) vs outline quad (expanded).

5. **`EditorModel` fold methods**: Correct. `fold_at_line/unfold_at_line/toggle_fold_at_line` look up fold by line, extract start, then delegate. `sync_folds` calls `update_layout()` after FoldMap sync. `detect_folds` collects buffer lines, detects regions, and syncs.

6. **`RenderLine` fold state** (`editor_view.rs`): Correct. `has_fold` and `is_collapsed` populated from `model.folding().folds().get(&buf_row)`.

7. **Test coverage**: 18 new tests covering fold_at, unfold_at, fold_all, unfold_all, fold_at_line, set_folds, indentation detection (basic, nested, blank lines, empty, single line), sync_to_fold_map (fold and unfold), visual_line_count, and multiple collapsed folds. 3 new tests for fold indicators. Excellent coverage.

#### Architecture Alignment

- Aligns with Phase 3 Step 4 plan: code folding with FoldMap sync and gutter indicators.
- `sync_to_fold_map()` bridges FoldingSystem to DisplayMap pipeline -- correct layer boundary.
- Fold indicators rendered in `prepaint()`/`paint()` following 3-phase Element lifecycle.
- Indentation-based fold detection is appropriate for markdown/code content.

### Step 5: Refine EditorView Input Handling

**Status**: REVIEWED
**Reviewer**: code-reviewer
**Commits**: `25331cf`
**Files Changed**: `editor_element.rs` (+26 lines), `editor_model.rs` (+43/-8 lines)

#### Safety Scan

| File | Symbol | Classification | Detail |
|------|--------|----------------|--------|
| `editor_element.rs` (scroll wheel handler) | Zero unwrap/expect/panic/unsafe/todo | PASS | |
| `editor_model.rs` (SelectUp/Down fix, fold shortcuts) | Zero unwrap/expect/panic/unsafe/todo | PASS | |

**Zero new prohibited symbols introduced in production code.**

#### BLOCKING Findings

None.

#### NON-BLOCKING Findings

**NB-17: `SelectRight` can exceed buffer bounds**

- **File**: `editor_model.rs:517-518`
- **Detail**: `self.state.select_to(pos + 1)` -- if `pos == buffer.len_chars()`, this passes `len_chars() + 1` to `select_to`. Whether this crashes depends on `select_to`'s behavior. Pre-existing issue (not introduced by Step 5), but noted since Step 5 touched adjacent code.
- **Severity**: LOW. The state machine likely clamps internally.

#### Correctness Assessment

1. **`SelectUp` fix** (`editor_model.rs:520-527`): Correct. Gets current line via `char_to_line(pos)`, guards `line > 0`, computes column, targets same column on previous line. `char_for_line_column` clamps column to line end. This is a proper selection extension (uses `select_to`) instead of the previous `move_up` which did not extend selection.

2. **`SelectDown` fix** (`editor_model.rs:529-537`): Correct. Same pattern as SelectUp but for next line. Guards `line + 1 < len_lines()`. Safe.

3. **Fold keyboard shortcuts** (`editor_model.rs:601-616`): Correct. `FoldRegion` -> `fold_at_line(cursor_line)`, `UnfoldRegion` -> `unfold_at_line(cursor_line)`, `FoldAll` -> `fold_all()`, `UnfoldAll` -> `unfold_all()`. All delegate to methods verified safe in Step 4 review.

4. **Scroll wheel handler** (`editor_element.rs:1131-1152`): Correct. Uses `event.delta.pixel_delta(line_height)` for consistent scroll speed. Applies to `viewport.scroll_y` and `scroll_x` with `.max(0.0)` clamping. Dispatch phase filter (`DispatchPhase::Bubble`) is correct. Model cloned before closure capture.

5. **Import additions**: `ScrollWheelEvent` import, fold action imports (`FoldRegion`, `UnfoldRegion`, `FoldAll`, `UnfoldAll`). Correct.

#### Architecture Alignment

- Aligns with Phase 3 Step 5 plan: refine input handling.
- SelectUp/Down now properly extend selection rather than just moving cursor.
- Fold shortcuts wired through the existing keybinding dispatch system.
- Scroll wheel uses GPUI's native `ScrollWheelEvent` with `pixel_delta` conversion.

### Out-of-Scope Commit: `c704243` (Main Window Dragging)

**Status**: REVIEWED (scope check)
**Commits**: `c704243`
**Files Changed**: `main_window.rs` (+76 lines, new file), 2 docs files (+168 lines)

#### Scope Assessment

This commit implements frameless window dragging in `pp-ui-mainwindow`. This is **NOT part of Phase 3: UI Feature Completion** which covers editor improvements only. This is a separate main-window feature. **SCOPE CREEP CONFIRMED.**

#### Safety Scan

| File | Symbol | Classification | Detail |
|------|--------|----------------|--------|
| `main_window.rs:164` | `.unwrap()` | **B-2** | Production code: `cx.open_window(...).unwrap()` -- panics if window creation fails |

**B-2: `.unwrap()` on `open_window()` in production code**

- **File**: `crates/pp-ui-mainwindow/src/main_window.rs:164`
- **Code**: `cx.open_window(...).unwrap();`
- **Risk**: If GPUI fails to create the window (GPU driver issue, display server error, resource exhaustion), this panics and crashes the application.
- **Fix**: Use `?` propagation or handle the error:

  ```rust
  cx.open_window(...).expect("Failed to open main window");
  // or better:
  if let Err(e) = cx.open_window(...) {
      eprintln!("Fatal: could not open window: {e}");
      std::process::exit(1);
  }
  ```

  Note: `.expect()` is also forbidden by project standards. The correct approach depends on whether `run_main_window_app` can return a Result.

---

## Summary

| Category | Pre-Phase 3 | Phase 3 Introduced | Status |
|----------|-------------|---------------------|--------|
| `unwrap()` in prod | 0 | 0 (editor crates) | PASS |
| `expect()` in prod | 0 | 0 (editor crates) | PASS |
| `panic!()` in prod | 0 | 0 (editor crates) | PASS |
| `unsafe` blocks | 2 (documented) | 0 | PASS |
| `todo!()` in prod | 0 | 0 | PASS |
| Clippy warnings | TBD | TBD | Pending |

**Phase 3 Editor Crates Verdict**: PASS -- Zero new safety violations introduced across Steps 1-5 in `pp-editor-main`, `pp-editor-core`, `pp-editor-events`. B-1 (composition range panic) identified and resolved.

**Out-of-Scope Finding**: `pp-ui-mainwindow/src/main_window.rs:164` has `.unwrap()` in production code (B-2). This is NOT a Phase 3 regression but was committed alongside Phase 3 work. Must be addressed separately.

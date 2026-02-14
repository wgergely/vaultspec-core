---
tags:
  - "#reference"
  - "#editor-demo"
date: 2026-02-05
related:
  - "[[2026-02-05-editor-demo-research]]"
  - "[[2026-02-04-displaymap-reference]]"
---

# Core Editor State Audit: pp-editor-core vs Zed editor

## Executive Summary

pp-editor-core is a framework-agnostic text editor foundation built on Ropey. Zed's editor is a full GPUI Entity with CRDT-capable text storage, anchor-based positioning, multi-cursor/multi-buffer support, and a declarative action dispatch system. This audit identifies five critical architectural differences and documents trade-offs for each.

---

## 1. State Management

### Our Pattern: `EditorState` Plain Struct

```
Crate: pp-editor-core
File: crates/pp-editor-core/src/state.rs
```

`EditorState` is a plain Rust struct owning all sub-components:

```rust
pub struct EditorState {
    buffer: Buffer,
    cursor: Cursor,
    history: History,
    dirty: bool,
    folds: Vec<FoldRegion>,
    display_map: DisplayMap,
}
```

- No framework dependency.
- No entity/reactivity system.
- Methods on `EditorState` directly mutate fields.
- Single cursor only (no multi-cursor).
- Flat ownership: buffer, cursor, history are all inline owned values.

### Zed Pattern: GPUI `Entity<Editor>`

```
Crate: editor
File: ref/zed/crates/editor/src/editor.rs:1128-1327
```

Zed's `Editor` struct has ~200 fields and is a GPUI Entity:

```rust
pub struct Editor {
    focus_handle: FocusHandle,
    buffer: Entity<MultiBuffer>,         // Reactive entity
    display_map: Entity<DisplayMap>,     // Reactive entity
    selections: SelectionsCollection,    // Multi-cursor
    scroll_manager: ScrollManager,
    // ... 190+ more fields
}
```

Key differences:

- **Reactive entities**: Buffer and DisplayMap are `Entity<T>` (GPUI managed, ref-counted, observable). Changes trigger re-renders automatically.
- **Event emission**: `impl EventEmitter<EditorEvent> for Editor {}` at `editor.rs:27440`. Edits, undo, redo, selection changes all emit events.
- **Multi-buffer**: `Entity<MultiBuffer>` supports editing multiple files in a single editor (e.g., search results, multi-cursor across files).

### Gap Assessment

| Aspect | pp-editor-core | Zed | Gap Severity |
|--------|---------------|-----|-------------|
| Reactivity | None (manual dirty flag) | Entity system with subscriptions | LOW for demo |
| Multi-buffer | Single buffer only | MultiBuffer with excerpts | LOW for demo |
| Event emission | None | EditorEvent enum | MEDIUM |
| Field count | 6 fields | ~200 fields | Expected |

**Recommendation**: For a demo, the plain struct approach is correct. The `dirty` flag + `version()` counter serves as a manual reactivity mechanism. When integrating with GPUI, wrap `EditorState` in an `Entity<T>` to gain automatic change notification. Do NOT attempt to replicate Zed's 200-field Editor struct.

---

## 2. Buffer Architecture

### Our Pattern: Ropey

```
Crate: pp-editor-core
File: crates/pp-editor-core/src/buffer.rs
```

```rust
pub struct Buffer {
    rope: Rope,        // Ropey 2.0
    version: u64,      // Monotonic counter
}
```

- Uses Ropey 2.0 API (byte-indexed internally, char-indexed API layer).
- O(log n) insert/delete, O(1) clone (copy-on-write).
- Version counter for dirty checking.
- No CRDT support; single-writer only.
- Line counting uses `LineType::LF` (configurable).

### Zed Pattern: Custom Rope + CRDT

```
Crate: text
File: ref/zed/crates/text/src/text.rs:52-61, 106-117
```

```rust
pub struct Buffer {
    snapshot: BufferSnapshot,
    history: History,
    deferred_ops: OperationQueue<Operation>,
    deferred_replicas: HashSet<ReplicaId>,
    pub lamport_clock: clock::Lamport,
    // ...
}

pub struct BufferSnapshot {
    replica_id: ReplicaId,
    remote_id: BufferId,
    visible_text: Rope,       // Custom rope impl
    deleted_text: Rope,       // For CRDT tombstones
    line_ending: LineEnding,
    undo_map: UndoMap,
    fragments: SumTree<Fragment>,
    insertions: SumTree<InsertionFragment>,
    // ...
    pub version: clock::Global,  // Vector clock
}
```

Key differences:

- **Custom Rope**: Zed has its own rope implementation in the `rope` crate. Not Ropey.
- **CRDT**: Uses Lamport clocks, vector clocks, replica IDs for collaborative editing.
- **Tombstone preservation**: `deleted_text` rope stores removed text for CRDT conflict resolution.
- **Fragment tree**: `SumTree<Fragment>` tracks insertion fragments for anchor resolution.
- **Snapshots**: `BufferSnapshot` is a cloneable, immutable view used for rendering.

### Trade-off Analysis

| Aspect | Ropey (ours) | Zed Custom Rope | Winner for Demo |
|--------|-------------|-----------------|-----------------|
| Complexity | Low | Very High (CRDT) | Ropey |
| Performance | Excellent for single-user | Excellent + collab | Tie |
| Unicode | Full support | Full support | Tie |
| Snapshot | O(1) clone | O(1) clone | Tie |
| Collaboration | Not supported | Full CRDT | Zed (if needed) |
| Maintenance | External crate | Internal (~3K LOC) | Ropey |

**Recommendation**: Ropey is the correct choice for our scope. The CRDT infrastructure in Zed is ~10K lines across `text`, `rope`, and `clock` crates, and is only needed for real-time collaboration. Our `version: u64` counter is sufficient for dirty-checking in a single-user context.

---

## 3. Cursor/Selection Model

### Our Pattern: Offset-Based Single Cursor

```
Crate: pp-editor-core
File: crates/pp-editor-core/src/cursor.rs
```

```rust
pub struct Selection {
    anchor: usize,    // Char offset
    head: usize,      // Char offset
}

pub struct Cursor {
    position: usize,           // Char offset
    selection: Option<Selection>,
    sticky_column: Option<usize>,
}
```

- Single cursor only.
- Offset-based: positions are `usize` character offsets.
- Offsets invalidate on every edit (must be manually adjusted).
- Selection is a simple anchor/head pair.
- `sticky_column` for vertical movement.

### Zed Pattern: Anchor-Based Multi-Cursor

```
Crate: text
File: ref/zed/crates/text/src/anchor.rs:9-21
File: ref/zed/crates/text/src/selection.rs:17-24
File: ref/zed/crates/editor/src/selections_collection.rs:27-37
```

```rust
// Anchor: stable position across edits
pub struct Anchor {
    pub timestamp: clock::Lamport,
    pub offset: usize,          // Offset into insertion fragment
    pub bias: Bias,             // Left or Right
    pub buffer_id: Option<BufferId>,
}

// Selection: generic over position type
pub struct Selection<T> {
    pub id: usize,
    pub start: T,
    pub end: T,
    pub reversed: bool,
    pub goal: SelectionGoal,    // HorizontalPosition(f64), etc.
}

// Multi-cursor collection
pub struct SelectionsCollection {
    next_selection_id: usize,
    line_mode: bool,
    disjoint: Arc<[Selection<Anchor>]>,
    pending: Option<PendingSelection>,
    select_mode: SelectMode,
    is_extending: bool,
}
```

Critical architectural differences:

1. **Anchors are stable across edits**: An `Anchor` references a position in the CRDT fragment tree by `(timestamp, offset)`. When text is inserted before the anchor, it automatically stays at the correct logical position. Our `usize` offsets become invalid after any edit.

2. **Multi-cursor**: `SelectionsCollection` manages `Arc<[Selection<Anchor>]>` -- an arbitrary number of non-overlapping selections plus one pending selection (e.g., drag-in-progress).

3. **Selection is generic over `T`**: `Selection<Anchor>` for storage, `Selection<Point>` or `Selection<usize>` for computation. The `.resolve()` method converts anchors to concrete positions.

4. **SelectionGoal**: Uses `HorizontalPosition(f64)` (pixel position) rather than column index for sticky column. This handles variable-width fonts correctly.

5. **Selection merging**: `SelectionsCollection::all()` merges the pending selection with disjoint selections, handling overlaps.

### Gap Assessment

| Aspect | pp-editor-core | Zed | Gap Severity |
|--------|---------------|-----|-------------|
| Multi-cursor | No | Yes | HIGH (future) |
| Position stability | Offsets invalidate | Anchors stable | HIGH (future) |
| Selection generics | Fixed `usize` | Generic `<T>` | MEDIUM |
| Sticky column | Column index | Pixel position | LOW |
| Selection modes | Character only | Character/Word/Line | MEDIUM |

**Recommendation**: For the demo, the single offset-based cursor is acceptable. The critical gap is offset invalidation -- currently `clamp_to_buffer()` is called after undo/redo, but insertions/deletions elsewhere do not update cursor position. For a multi-cursor future, a sum-tree-based anchor system (like our existing `sum_tree` module) would be the migration path. The `Selection<T>` generic pattern from Zed is worth adopting early.

---

## 4. Undo/Redo History

### Our Pattern: Operation Stack

```
Crate: pp-editor-core
File: crates/pp-editor-core/src/history.rs
```

```rust
pub enum Operation {
    Insert { pos: usize, text: Arc<str> },
    Delete { pos: usize, text: Arc<str> },
    Batch(Vec<Self>),
}

pub struct History {
    undo_stack: Vec<Operation>,
    redo_stack: Vec<Operation>,
    snapshot_interval: usize,
    ops_since_snapshot: usize,
}
```

- Simple stack-based model.
- Operations store `pos` as `usize` (char offset).
- `Batch` variant groups related operations.
- Undo inverts the operation and applies it.
- Redo replays the original operation.
- No transaction grouping by time.
- No selection history (cursor position not restored on undo).

### Zed Pattern: Transaction-Based History with Clock

```
Crate: text
File: ref/zed/crates/text/src/text.rs:120-153, 188-200
File: ref/zed/crates/text/src/undo_map.rs
File: ref/zed/crates/editor/src/editor.rs:13760-13817, 19456-19513
```

```rust
// Transaction = a group of edits
pub struct Transaction {
    pub id: TransactionId,        // Lamport timestamp
    pub edit_ids: Vec<clock::Lamport>,
    pub start: clock::Global,
}

struct History {
    base_text: Rope,
    operations: TreeMap<clock::Lamport, Operation>,
    undo_stack: Vec<HistoryEntry>,
    redo_stack: Vec<HistoryEntry>,
    transaction_depth: usize,     // Nested transactions
    group_interval: Duration,     // Auto-group within 300ms
}

// UndoMap: tracks undo counts per edit
pub struct UndoMap(SumTree<UndoMapEntry>);
```

Key differences:

1. **Transactions**: Edits are grouped into transactions. Multiple edits within a `transact()` closure form one undo unit. This is critical for compound operations (e.g., "rename symbol" = many edits across files, one undo).

2. **Time-based grouping**: `group_interval: Duration::from_millis(300)` -- rapid keystrokes are automatically merged into a single transaction.

3. **Selection history**: `Editor::undo()` at `editor.rs:13760` restores the selection state from before the transaction:

   ```rust
   if let Some((selections, _)) = self.selection_history.transaction(transaction_id).cloned() {
       self.change_selections(..., |s| s.select_anchors(selections.to_vec()));
   }
   ```

4. **UndoMap**: Instead of inverting operations, Zed tracks how many times each edit has been undone. Odd count = undone, even count = redone. This is a CRDT-compatible approach.

5. **Nested transactions**: `transaction_depth` supports nesting (start_transaction inside another transaction).

### Gap Assessment

| Aspect | pp-editor-core | Zed | Gap Severity |
|--------|---------------|-----|-------------|
| Transaction grouping | None (each op separate) | Time-based + explicit | HIGH |
| Selection restore | No | Yes | HIGH |
| Nested transactions | No | Yes | LOW |
| CRDT undo | No | UndoMap with counts | LOW for demo |
| Compound operations | `Batch` variant | Transactions | MEDIUM |

**Recommendation**: The most impactful improvement is **time-based transaction grouping**. Currently typing "Hello" creates 5 separate undo entries. Add a `group_interval: Duration` field to `History` and merge operations that arrive within the interval. Selection history restoration is also high-value -- save cursor state when pushing to undo stack, restore it on undo.

---

## 5. Command Dispatch

### Our Pattern: Procedural Handler

```
Crate: pp-editor-core
Files:
  - crates/pp-editor-core/src/input_handler.rs (StatefulInputHandler)
  - crates/pp-editor-core/src/api/commands.rs (CommandHandler trait)
  - crates/pp-editor-core/src/state.rs (direct methods)
```

Two dispatch mechanisms:

1. **StatefulInputHandler**: Big match statement mapping `KeyEvent` to operations. Receives `(&mut Buffer, &mut Cursor, &mut History)` as parameters.

2. **CommandHandler trait**: Async trait for `@command` completion (autocomplete providers). Not for editor actions.

3. **EditorState methods**: Direct method calls like `state.insert("text")`, `state.undo()`, etc.

### Zed Pattern: Declarative Action System

```
Crate: editor
Files:
  - ref/zed/crates/editor/src/actions.rs
  - ref/zed/crates/editor/src/editor.rs:24737-24752
```

```rust
// Declarative action definition with derive macro
#[derive(PartialEq, Clone, Deserialize, Default, JsonSchema, Action)]
#[action(namespace = editor)]
pub struct MoveToBeginningOfLine {
    pub stop_at_soft_wraps: bool,
    pub stop_at_indent: bool,
}

// Macro-generated simple actions
actions!(editor, [
    AcceptEditPrediction,
    Backspace,
    Cancel,
    Copy,
    Cut,
    // ... 100+ actions
]);

// Registration
pub fn register_action<A: Action>(
    &mut self, listener: fn(&mut Self, &A, &mut Window, &mut Context<Self>)
)
```

Key differences:

1. **Actions are types**: Each editor command is a Rust struct implementing the `Action` trait. This enables:
   - Serialization/deserialization (JSON keybindings)
   - Schema generation for documentation
   - Type-safe dispatch
   - Actions can carry parameters (e.g., `MoveToBeginningOfLine { stop_at_soft_wraps: true }`)

2. **Dispatch via GPUI**: Actions flow through GPUI's focus tree. The focused element receives the action first, then it bubbles up.

3. **Dynamic registration**: `register_action()` at `editor.rs:24752` allows runtime registration of action handlers, enabling plugins/extensions.

4. **Namespacing**: `#[action(namespace = editor)]` prevents action name collisions across crates.

### Gap Assessment

| Aspect | pp-editor-core | Zed | Gap Severity |
|--------|---------------|-----|-------------|
| Action typing | Match on key events | Typed structs | MEDIUM |
| Keybinding config | Hardcoded in handler | JSON-configurable | HIGH (future) |
| Parameters | None | Action struct fields | LOW |
| Bubbling | None | GPUI focus tree | LOW for demo |
| Extensibility | Add match arm | Register action | MEDIUM |

**Recommendation**: For the demo, the procedural approach is fine. The `StatefulInputHandler` match-based dispatch works. For the production editor, migrate to a typed action system:

1. Define actions as unit structs (or with params).
2. Create an `ActionRegistry` mapping `TypeId` to handler functions.
3. Dispatch by type rather than by key event pattern matching.

---

## Summary of Findings

### What We Have Right (Keep)

1. **Ropey as buffer backend** -- correct trade-off for non-collaborative editing.
2. **Framework-agnostic core** -- separating `pp-editor-core` from `pp-editor-main` (GPUI) is sound.
3. **Display map pipeline** -- 5-layer transform chain mirrors Zed's architecture.
4. **Operation-based history** -- inverse operations are the right primitive.
5. **Separation of concerns** -- buffer, cursor, history as distinct modules.

### Critical Gaps (Address for Demo)

| Priority | Gap | Effort | Impact |
|----------|-----|--------|--------|
| P0 | Transaction grouping (time-based undo merging) | LOW | Prevents 1-char-per-undo UX pain |
| P0 | Selection restore on undo/redo | LOW | Expected editor behavior |
| P1 | Selection modes (word, line) in SelectionsCollection | MEDIUM | Double-click/triple-click selection |
| P1 | `SelectionGoal` pixel-based sticky column | LOW | Correct vertical movement |

### Future Architecture Gaps (Post-Demo)

| Priority | Gap | Effort | Impact |
|----------|-----|--------|--------|
| P2 | Multi-cursor support | HIGH | Power-user feature |
| P2 | Anchor-based positions (stable across edits) | HIGH | Foundation for multi-cursor |
| P2 | Typed action dispatch system | MEDIUM | Keybinding configuration |
| P3 | Multi-buffer editing | VERY HIGH | Search results, multi-file editing |
| P3 | CRDT support | VERY HIGH | Real-time collaboration |

---

## Appendix: File Cross-Reference

### pp-editor-core Files Audited

- `crates/pp-editor-core/src/state.rs` -- EditorState (622 lines)
- `crates/pp-editor-core/src/buffer.rs` -- Buffer/Ropey (297 lines)
- `crates/pp-editor-core/src/cursor.rs` -- Cursor/Selection (182 lines)
- `crates/pp-editor-core/src/history.rs` -- History/Operation (197 lines)
- `crates/pp-editor-core/src/operations.rs` -- Editor operations (682 lines)
- `crates/pp-editor-core/src/input_handler.rs` -- Input dispatch (833 lines)
- `crates/pp-editor-core/src/input_types.rs` -- Input event types (125 lines)
- `crates/pp-editor-core/src/api/commands.rs` -- Command handler trait (142 lines)
- `crates/pp-editor-core/src/api/mod.rs` -- API module (12 lines)
- `crates/pp-editor-core/src/display_map/mod.rs` -- Display map (80+ lines)
- `crates/pp-editor-core/src/lib.rs` -- Crate root (93 lines)

### Zed Reference Files Audited

- `ref/zed/crates/editor/src/editor.rs` -- Editor entity (27K+ lines)
- `ref/zed/crates/editor/src/actions.rs` -- Action definitions
- `ref/zed/crates/editor/src/selections_collection.rs` -- Multi-cursor
- `ref/zed/crates/text/src/text.rs` -- Buffer + CRDT
- `ref/zed/crates/text/src/anchor.rs` -- Anchor system
- `ref/zed/crates/text/src/selection.rs` -- Generic selection
- `ref/zed/crates/text/src/undo_map.rs` -- CRDT undo tracking
- `ref/zed/crates/multi_buffer/src/multi_buffer.rs` -- Multi-buffer
- `ref/zed/crates/multi_buffer/src/anchor.rs` -- Multi-buffer anchors

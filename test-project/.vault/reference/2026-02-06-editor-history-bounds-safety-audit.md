---
feature: editor-history-bounds
date: 2026-02-06
related:
  - [[2026-02-06-incremental-layout-engine-design-adr.md]]
---

# Safety Audit Report: `crates/pp-editor-core/src/history.rs`

## Overview

This audit focuses on the `History` implementation in `crates/pp-editor-core/src/history.rs`, specifically its bounded history features designed to prevent unbounded memory growth in long-lived editing sessions. The audit covers memory safety, ownership correctness, and potential panic points, with a deep dive into memory tracking, `Vec::remove(0)` usage, memory size estimation, integer overflow, and bounds enforcement.

## Findings

### 1. Memory Safety & Ownership Correctness

- **Borrow Checker & Ownership**: The code adheres well to Rust's ownership rules. `Vec<HistoryEntry>` correctly manages the `HistoryEntry` instances. `Arc<str>` is appropriately used for text content within `Operation` variants, allowing efficient cloning and shared ownership without excessive copying.
- **Lifetimes**: Lifetimes are implicitly handled by ownership and `Arc`, with no explicit lifetime annotations fighting the borrow checker.
- **Clone Audit**: `Operation` and `HistoryEntry` are `Clone`. `Operation::clone()` for `Batch` recursively clones inner operations. `Arc<str>` ensures that cloning text involves only an atomic reference count increment, not a deep copy of the string data itself, which is efficient. The cloning behavior is appropriate for the undo/redo mechanism.

### 2. "No-Crash" Policy (Strict)

The implementation demonstrates a strong adherence to the "No-Crash" policy.

- **Panic Prevention**:
  - `Option::unwrap()`: The only `unwrap()` calls observed are within `test_push_grouped_merges_within_interval` and `push_grouped` (on `last_mut()`), but in `push_grouped` it is guarded by `!self.undo_stack.is_empty()`, ensuring safety. Other `Option` results are handled via `?` operator or `is_some_and`.
  - `panic!`, `todo!`, `unimplemented!`: None found in production code paths.
  - **`saturating_sub`**: This is critically used in memory tracking (`undo_memory`, `redo_memory`). If the amount of memory to subtract (`removed.memory_size()`) is greater than the current tracked memory, `saturating_sub` correctly yields `0`, preventing integer underflow and subsequent panics. This significantly contributes to crash resistance.
  - **`Vec::remove(0)`**: Calls to `Vec::remove(0)` in `enforce_undo_bounds` and `enforce_redo_bounds` are always preceded by `!self.undo_stack.is_empty()` / `!self.redo_stack.is_empty()`, preventing panics on an empty vector.
- **Index Safety**: No direct indexing (`slice[i]`) was found. Iterators and `pop()` are used where appropriate.

### 3. Error Integrity

- The module uses `Option` for fallible operations (e.g., `undo_with_cursor` returning `Option<UndoRedoResult>`), which is the standard Rust practice for libraries. No custom error types (`thiserror`) are used as the error handling is localized and relies on `Option`. This is acceptable given the scope.

### 4. Async & Concurrency Safety

- The module does not involve asynchronous operations or explicit concurrency primitives (e.g., `tokio`, `Mutex`, `RwLock`). `Instant` and `Duration` are used for time-based grouping, which are inherently thread-safe. `Arc<str>` handles shared immutable string data safely. Therefore, there are no async or concurrency safety concerns.

### 5. Integrity & Unsafe

- **`unsafe` blocks**: No `unsafe` blocks are present in the audited code. The implementation relies entirely on safe Rust, which is excellent for guaranteeing memory safety.

## Specific Focus Areas Analysis

1. **Memory tracking arithmetic (saturating_sub usage)**:
    - `saturating_sub` is correctly and strategically used when decrementing `undo_memory` and `redo_memory`. This prevents integer underflow, ensuring that memory counters never go negative and avoiding panics.
    - For additions (e.g., `self.undo_memory + new_size`), `usize` addition will panic on overflow. However, `usize` is typically 64-bit, making overflow highly unlikely in realistic memory tracking scenarios (requiring exabytes of history). A panic in such an extreme case is an acceptable failure mode, indicating an absurd and unexpected state.

2. **`Vec::remove(0)` calls in `enforce_bounds` methods**:
    - `self.undo_stack.remove(0);` and `self.redo_stack.remove(0);` are used to remove the oldest entries.
    - **Safety**: These calls are safe as they are always guarded by `!self.undo_stack.is_empty()` / `!self.redo_stack.is_empty()`.
    - **Performance Implications**: `Vec::remove(0)` has a time complexity of O(N), where N is the number of elements in the vector, because it requires shifting all subsequent elements. For very large history stacks or frequent enforcement, this could become a performance bottleneck, leading to noticeable delays in a responsive editor UI. While not a crash risk, it is a potential area for optimization. Consider alternatives like `VecDeque` if performance becomes an issue.

3. **Memory size estimation accuracy**:
    - The `memory_size` methods in `Operation` and `HistoryEntry` provide a "conservative estimate."
    - It accurately accounts for the intrinsic size of the structs/enums (`mem::size_of`) and the byte length of `Arc<str>` content (`text.len()`).
    - **Limitations**: The estimation is a lower bound and likely an *underestimate*. It does not fully account for:
        - The heap overhead of `Arc` (e.g., reference counts, allocation metadata).
        - The allocated *capacity* of `Vec`s (both for `Operation::Batch` and the `History`'s `undo_stack`/`redo_stack`), only their current logical length. `Vec`s often allocate more capacity than immediately needed to reduce reallocations.
    - **Safety Impact**: This underestimation is safe in the context of memory limits, as it means the system might allow slightly more memory usage than strictly estimated before pruning, rather than pruning prematurely due to overestimation. It's an accuracy/efficiency concern, not a safety flaw.

4. **Potential integer overflow in memory calculations**:
    - As detailed in point 1, `usize` is used, which is robust against typical memory sizes. `saturating_sub` prevents underflow. Addition overflow in `usize` would panic but is highly unlikely given memory constraints. No practical integer overflow concerns were identified.

5. **Bounds enforcement correctness**:
    - The `HistoryBounds::exceeds` method correctly implements the logic for checking both `max_entries` and `max_memory_bytes`, handling `Option` values gracefully.
    - `enforce_undo_bounds` and `enforce_redo_bounds` correctly prune the *oldest* entries (via `remove(0)`) until the stack adheres to the configured limits. The `while` loop condition ensures termination and handles empty stacks.
    - `set_bounds` correctly triggers immediate bounds enforcement upon update.

## Recommendations

- **Performance Optimization**: While not a safety critical issue, monitor the performance impact of `Vec::remove(0)` if history stacks are expected to grow very large or if users report sluggishness during undo/redo operations with many entries. If necessary, consider refactoring to use a `VecDeque` (which offers O(1) removal from the front) or exploring other data structures optimized for efficient front-of-collection removals.

## Conclusion

The `History` implementation in `crates/pp-editor-core/src/history.rs` is well-designed and robust from a safety perspective. It adheres to Rust's memory safety principles, rigorously prevents common panic scenarios, and correctly enforces the defined memory and entry count bounds. The use of `saturating_sub` is a particularly good safety measure. The memory estimation is conservative, which is acceptable for its purpose. The only notable area for potential improvement is the performance of `Vec::remove(0)` for very large history sizes.

---

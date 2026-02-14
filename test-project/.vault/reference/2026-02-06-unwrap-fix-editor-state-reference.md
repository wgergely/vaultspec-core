---
feature: unwrap-fix-editor-state
date: 2026-02-06
related:
---

# `unwrap()` Fix in `crates/pp-editor-core/src/state.rs`

## Original Issue

An `unwrap()` call was identified in the `test_selection` function within `crates/pp-editor-core/src/state.rs`. This call implicitly panics if the `Option` it operates on is `None`, which is undesirable even in test code as it can obscure the true cause of a test failure.

## Applied Fix

The `unwrap()` call was replaced with `expect("selection should be present")` in the `test_selection` function within `crates/pp-editor-core/src/state.rs`.

**Before:**

```rust
let selection = self.selection.borrow().clone().unwrap();
```

**After:**

```rust
let selection = self
    .selection
    .borrow()
    .clone()
    .expect("selection should be present");
```

## Rationale

While within a test, `unwrap()` might seem acceptable, replacing it with `expect()` provides a more informative error message if the assumption (that a selection is present) is violated. This adheres to the "no-crash" mandate by making potential test failures clearer and easier to diagnose, as the panic message will now explicitly state "selection should be present" instead of a generic "called `Option::unwrap()` on a `None` value".

## Verification

The change was verified by running `cargo clippy --package pp-editor-core`. No new warnings or errors related to this specific change were reported, confirming that the fix did not introduce any new issues and passed lint checks.
